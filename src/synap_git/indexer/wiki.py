from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from synap_git.config import SynapSettings
from synap_git.diagnostics.logger import get_logger
from synap_git.git.state import GitRepository
from synap_git.provider.factory import get_llm_provider
from synap_git.storage.sqlite import SynapStore

logger = get_logger("wiki_engine")

_EXCLUDED_PARTS = {
    ".git",
    ".synap",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
}
_EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".map",
    ".wasm",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
}
_PROJECT_PAGES = {
    "overview.md": "architecture/overview.md",
    "architecture.md": "architecture/system-architecture.md",
    "schema.md": "concepts/storage-and-data-model.md",
}


class WikiEngine:
    """Generate evidence-grounded engineering documentation with a local LLM."""

    def __init__(self, settings: SynapSettings, store: SynapStore) -> None:
        self.settings = settings
        self.store = store
        self.provider = get_llm_provider(settings)
        self.wiki_dir = self.settings.state_path / "wiki"
        self.wiki_dir.mkdir(parents=True, exist_ok=True)

    def generate_file_wiki(self, file_id: str, file_path: str, content: str) -> None:
        self.store.enqueue_wiki(file_path)

    def generate_module_wiki(self, dir_path: str) -> None:
        self.store.enqueue_wiki(dir_path)

    def generate_project_wiki(self) -> None:
        for page in ("overview.md", "architecture.md", "schema.md"):
            self.store.enqueue_wiki(page)

    def _files(self) -> list[str]:
        """Return tracked and relevant untracked paths, in deterministic order."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=self.settings.repository_path,
                capture_output=True,
                text=True,
                check=True,
            )
            paths = result.stdout.splitlines()
        except (OSError, subprocess.CalledProcessError) as exc:
            logger.warning("wiki_git_file_scan_failed", error=str(exc))
            paths = [
                p.relative_to(self.settings.repository_path).as_posix()
                for p in self.settings.repository_path.rglob("*")
            ]
        return sorted(
            p
            for p in paths
            if p
            and not any(part in _EXCLUDED_PARTS for part in Path(p).parts)
            and Path(p).suffix.lower() not in _EXCLUDED_SUFFIXES
            and (self.settings.repository_path / p).is_file()
        )

    def _safe_source_path(self, path: str) -> str:
        candidate = Path(path)
        if candidate.is_absolute():
            raise ValueError("source path must be repository-relative")
        root = self.settings.repository_path.resolve()
        resolved = (root / candidate).resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("source path escapes the repository") from exc

    def _tree(self, paths: list[str]) -> str:
        root: dict[str, Any] = {}
        for path in paths:
            cursor = root
            parts = Path(path).parts
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor.setdefault(parts[-1], None)
        lines = [
            "# Exact codebase tree",
            "",
            "This tree is generated from Git-visible repository paths. Generated state, caches, dependencies, and binary build outputs are excluded.",
            "",
            "```text",
            f"{self.settings.repository_path.name}/",
        ]

        def render(node: dict[str, Any], prefix: str = "") -> None:
            entries = sorted(node.items())
            for index, (name, child) in enumerate(entries):
                last = index == len(entries) - 1
                lines.append(
                    f"{prefix}{'└── ' if last else '├── '}{name}{'/' if isinstance(child, dict) else ''}"
                )
                if isinstance(child, dict):
                    render(child, prefix + ("    " if last else "│   "))

        render(root)
        lines.extend(
            [
                "```",
                "",
                "## Exclusion policy",
                "",
                "`.git/`, `.synap/`, virtual environments, dependency installs, caches, build outputs, and binary/minified artifacts are excluded so the tree describes the maintainable repository rather than generated state.",
                "",
                "## File reference index",
                "",
                "| Exact path | Documentation |",
                "|---|---|",
            ]
        )
        lines.extend(f"| `{path}` | [File explanation](files/{path}.md) |" for path in paths)
        lines.append("")
        return "\n".join(lines) + "\n"

    def _evidence(self, path: str) -> dict[str, Any]:
        source = self.settings.repository_path / path
        content = source.read_text(encoding="utf-8", errors="replace")
        entry = self.store.get_file_by_path(path)
        symbols = self.store.get_symbols_by_file(entry["file_id"]) if entry else []
        imports = [
            line.strip()
            for line in content.splitlines()
            if re.match(r"^(import |from |require\(|#include )", line.strip())
        ]
        relationships: list[dict[str, Any]] = []
        for symbol in symbols[:30]:
            for direction in ("upstream", "downstream"):
                for neighbor in self.store.get_neighborhood(
                    symbol["symbol_id"], depth=1, max_neighbors=20, direction=direction
                )[1:]:
                    relationships.append(
                        {
                            "symbol": symbol["name"],
                            "direction": direction,
                            "name": neighbor["name"],
                            "path": neighbor["source_path"],
                        }
                    )
        return {
            "path": path,
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "lines": len(content.splitlines()),
            "language": entry.get("language") if entry else source.suffix.lstrip(".") or "unknown",
            "git_oid": entry.get("git_oid") if entry else None,
            "symbols": [
                {"name": s["name"], "kind": s["kind"], "lines": [s["start_line"], s["end_line"]]}
                for s in symbols
            ],
            "imports": imports[:80],
            "relationships": relationships[:120],
            "source": content[:12000],
        }

    def _manifest(self, paths: list[str], evidence: list[dict[str, Any]]) -> dict[str, Any]:
        git_state = GitRepository(self.settings.repository_path).state(force=True)
        return {
            "repository_revision": git_state.head_commit,
            "branch": git_state.effective_branch,
            "generated_at": datetime.now(UTC).isoformat(),
            "generation_model": getattr(self.provider, "default_model", None),
            "directories": len({str(Path(p).parent) for p in paths}),
            "discovered_files": len(paths),
            "documented_files": len(evidence),
            "coverage": 1.0 if not paths else len(evidence) / len(paths),
            "excluded_paths": sorted(_EXCLUDED_PARTS),
            "unsupported_files": [],
            "files": {
                item["path"]: {"sha256": item["sha256"], "lines": item["lines"]}
                for item in evidence
            },
        }

    def _write_atomic(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            Path(tmp_name).replace(path)
        except Exception:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass
            raise

    def _generate(self, target: str, evidence: dict[str, Any], instruction: str) -> str:
        if self.provider is None:
            raise RuntimeError(
                "Local LLM is unavailable. Configure Ollama and retry; existing wiki files were preserved."
            )
        system = "You are Synap's local engineering-documentation author. Write clear professional English. Use only supplied evidence. Never invent files, symbols, calls, routes, or relationships. Cite supplied paths and line ranges for factual claims. Mark uncertainty as unknown or inferred. Return Markdown only."
        prompt = f"Target: {target}\nTask: {instruction}\nEvidence JSON:\n{json.dumps(evidence, indent=2)}"
        last_error = "empty response"
        for attempt in range(2):
            response = self.provider.generate(
                system_prompt=system,
                user_prompt=prompt
                if attempt == 0
                else prompt + "\nReturn a concise Markdown document now.",
                max_tokens=900,
            )
            content = response.content.strip()
            if content:
                return content + "\n"
            last_error = "empty response"
        raise ValueError(f"Local LLM returned invalid Markdown for {target}: {last_error}")

    def _file_doc(self, evidence: dict[str, Any]) -> str:
        return self._generate(
            evidence["path"],
            evidence,
            "Explain what this file is, why it exists, exact responsibilities, symbols, dependencies, callers if evidenced, data and side effects, execution participation, and modification risks. Include source references.",
        )

    def _navigation(self, paths: list[str]) -> None:
        rows = [f"| `{path}` | [Explanation](files/{path}.md) |" for path in paths]
        self._write_atomic(
            self.wiki_dir / "README.md",
            "# Synap engineering wiki\n\nThis wiki is generated from Synap's structural index and the configured local LLM. Start with the exact [codebase tree](codebase-tree.md), then read the [architecture overview](architecture/overview.md), [request flows](flows/request-lifecycle.md), and [engineering concepts](concepts/engineering-concepts.md). File explanations live under `files/`; generation evidence and freshness metadata live under `generated/`. Regenerate with `synap wiki generate --incremental` or rebuild with `synap wiki generate --full`.\n",
        )
        self._write_atomic(
            self.wiki_dir / "file-index.md",
            "# File index\n\n| Exact source path | Documentation |\n|---|---|\n"
            + "\n".join(rows)
            + "\n",
        )
        for directory, title, body in (
            ("architecture", "Architecture", "Architecture explanations and system boundaries."),
            ("flows", "Request flows", "Execution paths for CLI, API, and MCP requests."),
            (
                "modules",
                "Modules",
                "Directory-level explanations generated from grouped source evidence.",
            ),
            ("files", "Files", "One evidence-grounded explanation per relevant source file."),
            (
                "concepts",
                "Engineering concepts",
                "Project-specific explanations of concepts used by Synap.",
            ),
            (
                "integrations",
                "Integrations",
                "External services and integration boundaries found in the repository.",
            ),
        ):
            self._write_atomic(self.wiki_dir / directory / "README.md", f"# {title}\n\n{body}\n")

    def generate(self, *, full: bool = False) -> dict[str, Any]:
        """Generate the complete wiki or only changed file pages."""
        paths = self._files()
        evidence = [self._evidence(path) for path in paths]
        manifest = self._manifest(paths, evidence)
        manifest_path = self.wiki_dir / "generated" / "generation-manifest.json"
        old_manifest: dict[str, Any] = {}
        if manifest_path.exists() and not full:
            try:
                old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("wiki_manifest_read_failed", error=str(exc))
        if self.provider is None:
            raise RuntimeError(
                "Local LLM is unavailable. Configure Ollama and retry; existing wiki files were preserved."
            )
        self._write_atomic(self.wiki_dir / "codebase-tree.md", self._tree(paths))
        self._navigation(paths)
        self._write_atomic(
            self.wiki_dir / "generated" / "evidence.json", json.dumps(evidence, indent=2) + "\n"
        )
        changed = [
            item
            for item in evidence
            if full
            or old_manifest.get("files", {}).get(item["path"], {}).get("sha256") != item["sha256"]
        ]
        failures: list[str] = []
        pending_pages: dict[Path, str] = {}
        for item in changed:
            try:
                pending_pages[self.wiki_dir / "files" / f"{item['path']}.md"] = self._file_doc(item)
            except Exception as exc:
                failures.append(f"{item['path']}: {exc}")
                logger.error("wiki_generation_failed", path=item["path"], error=str(exc))
        if full or changed:
            project_evidence = {"repository": manifest, "files": evidence[:80]}
            targets = {
                "architecture/overview.md": "Describe actual architecture, entry points, and reading order.",
                "architecture/system-architecture.md": "Explain components, boundaries, dependencies, and runtime responsibilities.",
                "architecture/component-map.md": "Map actual components to their source files and responsibilities.",
                "architecture/dependency-map.md": "Explain verified import and symbol relationships. Do not infer missing edges.",
                "architecture/data-flow.md": "Explain actual data movement and storage interactions.",
                "flows/application-startup.md": "Trace application and daemon startup from real entry points.",
                "flows/request-lifecycle.md": "Trace important CLI, API, and MCP request paths with Mermaid diagrams and source references.",
                "flows/authentication-flow.md": "Document authentication or explicitly state that no authentication flow is evidenced.",
                "flows/database-flow.md": "Trace SQLite initialization, reads, writes, and WAL behavior with source references.",
                "flows/error-handling-flow.md": "Trace provider, CLI, API, and worker failure paths with source references.",
                "concepts/engineering-concepts.md": "Explain only engineering concepts evidenced by this repository, in project context with limits.",
                "concepts/architecture-decisions.md": "Extract only decisions evidenced by comments, docs, or code. Mark inferred decisions.",
                "concepts/design-patterns.md": "Explain patterns actually used by the code, not generic textbook patterns.",
                "concepts/storage-and-data-model.md": "Explain actual SQLite tables, relationships, and persistence behavior.",
                "integrations/overview.md": "Describe actual external services, providers, MCP, Git, and filesystem boundaries.",
            }
            for target, instruction in targets.items():
                try:
                    pending_pages[self.wiki_dir / target] = self._generate(
                        target, project_evidence, instruction
                    )
                except Exception as exc:
                    failures.append(f"{target}: {exc}")
                    logger.error("wiki_project_generation_failed", page=target, error=str(exc))
            module_paths = sorted(
                {
                    str(Path(item["path"]).parent)
                    for item in evidence
                    if str(Path(item["path"]).parent) != "."
                }
            )
            for module_path in module_paths:
                module_evidence = {
                    "module": module_path,
                    "files": [
                        item for item in evidence if str(Path(item["path"]).parent) == module_path
                    ],
                }
                target = f"modules/{module_path}.md"
                try:
                    pending_pages[self.wiki_dir / target] = self._generate(
                        target,
                        module_evidence,
                        "Explain this module's purpose, boundaries, public entry points, dependencies, data, callers, and safe modification points.",
                    )
                except Exception as exc:
                    failures.append(f"{target}: {exc}")
                    logger.error("wiki_module_generation_failed", page=target, error=str(exc))
        if failures:
            manifest["generation_status"] = "failed"
            manifest["failed_documents"] = failures
            self._write_atomic(manifest_path, json.dumps(manifest, indent=2) + "\n")
            raise RuntimeError("Wiki generation completed with failures:\n" + "\n".join(failures))
        for page, content in pending_pages.items():
            self._write_atomic(page, content)
        if not full:
            current_paths = {item["path"] for item in evidence}
            for removed in set(old_manifest.get("files", {})) - current_paths:
                removed_page = self.wiki_dir / "files" / f"{removed}.md"
                try:
                    removed_page.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("wiki_removed_page_cleanup_failed", path=removed, error=str(exc))
        manifest["generation_status"] = "complete"
        manifest["failed_documents"] = []
        self._write_atomic(manifest_path, json.dumps(manifest, indent=2) + "\n")
        return {
            "files": len(paths),
            "generated": len(changed),
            "revision": manifest["repository_revision"],
        }

    def status(self) -> dict[str, Any]:
        paths = self._files()
        manifest_path = self.wiki_dir / "generated" / "generation-manifest.json"
        if not manifest_path.exists():
            return {"state": "missing", "files": len(paths), "stale": len(paths)}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"state": "invalid", "files": len(paths), "stale": len(paths)}
        if manifest.get("generation_status") != "complete":
            return {
                "state": "stale",
                "files": len(paths),
                "stale": manifest.get("failed_documents", paths),
                "revision": manifest.get("repository_revision"),
            }
        current = {p: self._evidence(p)["sha256"] for p in paths}
        stale = [
            p
            for p, digest in current.items()
            if manifest.get("files", {}).get(p, {}).get("sha256") != digest
        ]
        stale.extend(sorted(set(manifest.get("files", {})) - set(current)))
        return {
            "state": "stale" if stale else "fresh",
            "files": len(paths),
            "stale": stale,
            "revision": manifest.get("repository_revision"),
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not (self.wiki_dir / "generated" / "generation-manifest.json").exists():
            errors.append("missing generated/generation-manifest.json")
        if not (self.wiki_dir / "codebase-tree.md").exists():
            errors.append("missing codebase-tree.md")
        try:
            manifest_data = json.loads(
                (self.wiki_dir / "generated" / "generation-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            if manifest_data.get("generation_status") != "complete":
                errors.append("generation manifest is not complete")
            for source_path in manifest_data.get("files", {}):
                if not (self.wiki_dir / "files" / f"{source_path}.md").exists():
                    errors.append(f"missing file documentation: {source_path}")
        except (OSError, json.JSONDecodeError):
            pass
        for page in self.wiki_dir.rglob("*.md"):
            text = page.read_text(encoding="utf-8", errors="replace")
            if text.count("```") % 2:
                errors.append(f"unbalanced Markdown fences: {page.relative_to(self.wiki_dir)}")
            if (
                text.count("```mermaid") > 0
                and "flowchart " not in text
                and "sequenceDiagram" not in text
                and "classDiagram" not in text
                and "erDiagram" not in text
            ):
                errors.append(
                    f"Mermaid fence has no recognized diagram: {page.relative_to(self.wiki_dir)}"
                )
        return errors

    def ensure_wiki_page(self, wiki_filepath: str) -> None:
        target = wiki_filepath if wiki_filepath.endswith(".md") else f"{wiki_filepath}.md"
        if target.startswith("files/"):
            source_path = self._safe_source_path(target.removeprefix("files/")[:-3])
            target_path = self.wiki_dir / "files" / f"{source_path}.md"
        elif target in _PROJECT_PAGES:
            target_path, source_path = self.wiki_dir / _PROJECT_PAGES[target], target
        else:
            source_path = self._safe_source_path(target[:-3])
            target_path = self.wiki_dir / f"{source_path}.md"
        if target_path.exists() and self.status().get("state") == "fresh":
            return
        if (self.settings.repository_path / source_path).is_file():
            self._write_atomic(target_path, self._file_doc(self._evidence(source_path)))
            return
        self.generate(full=False)

    def generate_file_wiki_sync(self, file_path: str, content: str, git_oid: str) -> None:
        self.ensure_wiki_page(f"files/{file_path}.md")

    def generate_project_wiki_page_sync(self, page_name: str) -> None:
        self.generate(full=False)
