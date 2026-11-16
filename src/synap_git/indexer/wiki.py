from __future__ import annotations

import ast
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
from synap_git.indexer.scanner import GitIgnoreSpec, _is_binary_file
from synap_git.parser.registry import CodeParserRegistry
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
    ".cache",
    "vendor",
    "target",
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
    ".lock",
    ".min.js",
    ".min.css",
}


class WikiEngine:
    """
    Generate evidence-grounded engineering documentation mirroring the repository
    1:1 under `.synap/wiki/` with deterministic Zero-LLM fallback from SQLite AST tables.
    """

    def __init__(self, settings: SynapSettings, store: SynapStore) -> None:
        self.settings = settings
        self.store = store
        self.provider = get_llm_provider(settings)
        self.wiki_dir = self.settings.state_path / "wiki"
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.wiki_dir / ".manifest.json"

    def generate_file_wiki(self, file_id: str, file_path: str, content: str) -> None:
        """Enqueue file for background wiki generation."""
        self.store.enqueue_wiki(file_path)

    def generate_file_wiki_sync(self, file_path: str, content: str, git_oid: str) -> None:
        """Synchronously generate or update a single file wiki page."""
        self.ensure_wiki_page(file_path)

    def generate_module_wiki(self, dir_path: str) -> None:
        """No-op: synthetic module documentation is disallowed."""

    def generate_project_wiki(self) -> None:
        """Synchronously regenerate documentation for repository files."""
        self.generate(full=False)

    def generate_project_wiki_page_sync(self, page_name: str) -> None:
        """No-op: synthetic project documentation is disallowed."""

    def _safe_source_path(self, path: str) -> str:
        """Ensure path is repository-relative and does not escape root."""
        candidate = Path(path)
        if candidate.is_absolute():
            raise ValueError("source path must be repository-relative")
        root = self.settings.repository_path.resolve()
        resolved = (root / candidate).resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("source path escapes the repository") from exc

    def _resolve_source_path(self, path_str: str) -> str:
        """Normalize input path to a clean relative source path."""
        cleaned = path_str.strip()
        if cleaned.startswith("files/"):
            cleaned = cleaned.removeprefix("files/")
        if cleaned.endswith(".md"):
            cleaned = cleaned[:-3]
        return self._safe_source_path(cleaned)

    def _write_atomic(self, path: Path, content: str) -> None:
        """Write content atomically via temporary file replacement."""
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

    def _load_manifest(self) -> dict[str, Any]:
        """Load manifest tracking file hashes and generation metadata."""
        if not self.manifest_path.exists():
            return {}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("wiki_manifest_read_failed", error=str(exc))
            return {}

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        """Persist manifest atomically."""
        self._write_atomic(self.manifest_path, json.dumps(manifest, indent=2) + "\n")

    def _compute_sha256(self, rel_path: str) -> str:
        """Compute sha256 hex digest of source file."""
        abs_path = self.settings.repository_path / rel_path
        try:
            return hashlib.sha256(abs_path.read_bytes()).hexdigest()
        except OSError:
            return ""

    def _files(self) -> list[str]:
        """Return tracked and relevant untracked paths, filtered and deterministically sorted."""
        root = self.settings.repository_path.resolve()
        paths: list[str] = []
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=root,
                capture_output=True,
                check=True,
            )
            for raw_path in result.stdout.split(b"\0"):
                if raw_path:
                    try:
                        paths.append(raw_path.decode("utf-8"))
                    except UnicodeDecodeError:
                        pass
        except (OSError, subprocess.CalledProcessError) as exc:
            logger.warning("wiki_git_file_scan_failed", error=str(exc))
            gitignore = None
            gitignore_path = root / ".gitignore"
            if gitignore_path.exists():
                try:
                    gitignore = GitIgnoreSpec(root, gitignore_path.read_text("utf-8").splitlines())
                except Exception:
                    pass
            for file_entry_path in root.rglob("*"):
                if file_entry_path.is_file():
                    try:
                        rel = file_entry_path.relative_to(root).as_posix()
                        if gitignore and gitignore.matches(file_entry_path, is_dir=False):
                            continue
                        paths.append(rel)
                    except ValueError:
                        pass

        filtered: list[str] = []
        for str_path in paths:
            if not str_path:
                continue
            path_obj = Path(str_path)
            if any(part in _EXCLUDED_PARTS for part in path_obj.parts):
                continue
            if path_obj.suffix.lower() in _EXCLUDED_SUFFIXES:
                continue
            abs_p = root / path_obj
            if not abs_p.is_file():
                continue
            try:
                stat = abs_p.stat()
                if stat.st_size > self.settings.max_file_bytes:
                    continue
            except OSError:
                continue
            if _is_binary_file(abs_p):
                continue
            filtered.append(str_path)

        return sorted(set(filtered))

    def _extract_module_docstring(self, content: str) -> str | None:
        """Extract module-level docstring from Python code."""
        try:
            parsed_ast = ast.parse(content)
            return ast.get_docstring(parsed_ast)
        except Exception:
            return None

    def _extract_leading_comment(self, content: str) -> str | None:
        """Extract leading comment block as purpose fallback for non-Python or docstringless files."""
        lines = content.splitlines()
        comment_lines: list[str] = []
        in_block = False
        for line in lines[:40]:
            stripped = line.strip()
            if not stripped:
                if comment_lines:
                    break
                continue
            if stripped.startswith("/*"):
                in_block = True
                cleaned = stripped.removeprefix("/*").removesuffix("*/").strip()
                if cleaned:
                    comment_lines.append(cleaned)
                if "*/" in stripped and stripped != "/*":
                    in_block = False
                continue
            if in_block:
                if "*/" in stripped:
                    in_block = False
                    cleaned = stripped.removesuffix("*/").strip()
                    if cleaned:
                        comment_lines.append(cleaned)
                    break
                comment_lines.append(stripped.lstrip("* ").strip())
                continue
            if stripped.startswith("//") or stripped.startswith("#"):
                if stripped.startswith("#!"):
                    continue
                comment_lines.append(stripped.lstrip("/# ").strip())
            else:
                break
        return "\n".join(comment_lines) if comment_lines else None

    def _extract_signature(
        self, lines: list[str], start_line: int, end_line: int, language: str
    ) -> str:
        """Extract clean symbol signature with parameter types and return type."""
        s_idx = max(0, start_line - 1)
        if s_idx >= len(lines):
            return ""
        sig_lines: list[str] = []
        for i in range(s_idx, min(len(lines), s_idx + 8)):
            line = lines[i]
            sig_lines.append(line)
            stripped = line.strip()
            if language == "python" and stripped.endswith(":"):
                break
            if language != "python" and (stripped.endswith("{") or stripped.endswith(";")):
                break
            if i >= end_line - 1:
                break
        return "\n".join(sig_lines).strip()

    def _evidence(self, path: str) -> dict[str, Any]:
        """Gather structural AST evidence, imports, dependencies, callers, and decisions."""
        abs_path = self.settings.repository_path / path
        content = abs_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        file_entry = self.store.get_file_by_path(path)
        raw_lang = file_entry.get("language") if file_entry else None
        language = str(raw_lang) if raw_lang else (abs_path.suffix.lstrip(".") or "unknown")
        file_id = file_entry["file_id"] if file_entry else None

        # Extract module docstring or comment purpose
        module_docstring = (
            self._extract_module_docstring(content)
            if language == "python"
            else self._extract_leading_comment(content)
        )

        # Extract symbols
        symbols: list[dict[str, Any]] = []
        if file_id:
            symbols = self.store.get_symbols_by_file(file_id)
        if not symbols:
            parsed = CodeParserRegistry().parse(abs_path, relative_path=path, text=content)
            symbols = [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                }
                for s in parsed.symbols
            ]

        # Extract function/class docstrings if Python
        symbol_docstrings: dict[tuple[str, int], str] = {}
        if language == "python":
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                        ds = ast.get_docstring(node)
                        if ds:
                            symbol_docstrings[(node.name, node.lineno)] = ds
            except Exception:
                pass

        # Filter public symbols
        public_symbols: list[dict[str, Any]] = []
        for s in symbols:
            name = s["name"]
            if name.startswith("_") and not name.startswith("__init__"):
                continue
            sig = self._extract_signature(lines, s["start_line"], s["end_line"], language)
            ds = symbol_docstrings.get((name, s["start_line"]))
            public_symbols.append(
                {
                    "name": name,
                    "kind": s["kind"],
                    "start_line": s["start_line"],
                    "end_line": s["end_line"],
                    "signature": sig,
                    "docstring": ds,
                }
            )

        # Direct imports in file
        direct_imports = [
            line.strip()
            for line in lines
            if re.match(r"^(import |from |require\(|#include |use |export )", line.strip())
        ]

        # Graph dependencies (callees) and callers
        callees: list[dict[str, str]] = []
        callers: list[dict[str, str]] = []
        if file_id:
            try:
                with self.store.connect() as conn:
                    callee_rows = conn.execute(
                        """
                        SELECT DISTINCT s.name as symbol, t.name as callee_symbol, tf.path as callee_file
                        FROM edges e
                        JOIN symbols s ON e.source_symbol = s.symbol_id
                        JOIN symbols t ON e.target_symbol = t.symbol_id
                        JOIN files tf ON t.file_id = tf.file_id
                        WHERE s.file_id = ?
                        ORDER BY tf.path, t.name
                        LIMIT 50
                        """,
                        (file_id,),
                    ).fetchall()
                    callees = [dict(r) for r in callee_rows]

                    caller_rows = conn.execute(
                        """
                        SELECT DISTINCT s.name as caller_symbol, sf.path as caller_file, t.name as symbol
                        FROM edges e
                        JOIN symbols s ON e.source_symbol = s.symbol_id
                        JOIN files sf ON s.file_id = sf.file_id
                        JOIN symbols t ON e.target_symbol = t.symbol_id
                        WHERE t.file_id = ?
                        ORDER BY sf.path, s.name
                        LIMIT 50
                        """,
                        (file_id,),
                    ).fetchall()
                    callers = [dict(r) for r in caller_rows]
            except Exception as exc:
                logger.warning("wiki_edge_query_failed", path=path, error=str(exc))

        # Architectural decisions impacting this file
        decisions: list[dict[str, Any]] = []
        try:
            with self.store.connect() as conn:
                d_rows = conn.execute(
                    """
                    SELECT decision_id, branch, commit_hash, content, context, created_at
                    FROM decisions
                    WHERE context LIKE ? OR content LIKE ?
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    (f"%{path}%", f"%{path}%"),
                ).fetchall()
                if not d_rows and abs_path.name:
                    d_rows = conn.execute(
                        """
                        SELECT decision_id, branch, commit_hash, content, context, created_at
                        FROM decisions
                        WHERE context LIKE ? OR content LIKE ?
                        ORDER BY created_at DESC
                        LIMIT 5
                        """,
                        (f"%{abs_path.name}%", f"%{abs_path.name}%"),
                    ).fetchall()
                decisions = [dict(r) for r in d_rows]
        except Exception as exc:
            logger.warning("wiki_decisions_query_failed", path=path, error=str(exc))

        return {
            "path": path,
            "sha256": sha256,
            "language": language,
            "lines": len(lines),
            "git_oid": file_entry.get("git_oid") if file_entry else None,
            "module_docstring": module_docstring,
            "public_symbols": public_symbols,
            "imports": direct_imports[:60],
            "callees": callees,
            "callers": callers,
            "decisions": decisions,
        }

    def _render_page(
        self,
        evidence: dict[str, Any],
        llm_summary: str | None = None,
    ) -> str:
        """Deterministically render high-signal markdown page with optional LLM augmentation."""
        path = evidence["path"]
        language = evidence["language"]
        lines = evidence["lines"]
        docstring = evidence["module_docstring"]
        symbols = evidence["public_symbols"]
        imports = evidence["imports"]
        callees = evidence["callees"]
        callers = evidence["callers"]
        decisions = evidence["decisions"]

        parts: list[str] = [f"# `{path}`", ""]

        # File purpose & module docstring
        if docstring:
            parts.extend(["> " + "\n> ".join(docstring.splitlines()), ""])
        else:
            parts.extend([f"Source file for `{path}` ({language}).", ""])

        # Overview
        parts.extend(
            [
                "## Overview",
                f"- **Path**: `{path}`",
                f"- **Language**: `{language}`",
                f"- **Lines**: {lines}",
                "",
            ]
        )

        # Optional LLM-synthesized behavioral summary and gotchas
        if llm_summary:
            parts.extend([llm_summary.strip(), ""])

        # Public Symbols, classes, functions with signatures & types
        parts.extend(["## Public Symbols & Interfaces", ""])
        if symbols:
            for s in symbols:
                kind = s["kind"].replace("_definition", "").replace("_declaration", "")
                parts.append(f"### `{kind}` `{s['name']}`")
                parts.append(f"- **Lines**: L{s['start_line']}-L{s['end_line']}")
                if s["signature"]:
                    parts.extend([f"```{language}", s["signature"], "```"])
                if s["docstring"]:
                    parts.extend(["", s["docstring"].strip()])
                parts.append("")
        else:
            parts.extend(["No public classes or functions declared in this file.", ""])

        # Imports & dependencies
        parts.extend(["## Imports & Dependencies", ""])
        if imports:
            parts.append("### Direct Imports")
            for imp in imports:
                parts.append(f"- `{imp}`")
            parts.append("")

        if callees:
            parts.append("### Graph Dependencies (Callees)")
            for c in callees:
                parts.append(
                    f"- `{c['callee_file']}`: `{c['callee_symbol']}` (via `{c['symbol']}`)"
                )
            parts.append("")

        if not imports and not callees:
            parts.extend(["No external dependencies identified.", ""])

        # Callers & Callees
        parts.extend(["## Callers & Callees", ""])
        parts.append("### Callers (Dependants)")
        if callers:
            for cl in callers:
                parts.append(
                    f"- `{cl['caller_file']}`: `{cl['caller_symbol']}` -> calls `{cl['symbol']}`"
                )
        else:
            parts.append("No external callers recorded in the graph.")
        parts.append("")

        parts.append("### Callees (Dependencies)")
        if callees:
            for c in callees:
                parts.append(
                    f"- `{c['callee_file']}`: `{c['callee_symbol']}` (from `{c['symbol']}`)"
                )
        else:
            parts.append("No external callees recorded in the graph.")
        parts.append("")

        # Architectural decisions impacting this file
        parts.extend(["## Architectural Decisions", ""])
        if decisions:
            for d in decisions:
                commit = d.get("commit_hash", "")[:7]
                parts.append(f"- **Decision** (`{commit}`): {d['content']}")
                if d.get("context"):
                    parts.append(f"  * Context: {d['context']}")
            parts.append("")
        else:
            parts.extend(["No architectural decisions recorded for this file.", ""])

        return "\n".join(parts) + "\n"

    def _augment_with_llm(self, evidence: dict[str, Any]) -> str | None:
        """Synthesize behavioral summary and gotchas if local LLM is available."""
        if self.provider is None:
            return None

        prompt_evidence = {
            "path": evidence["path"],
            "language": evidence["language"],
            "symbols": [s["name"] for s in evidence["public_symbols"][:20]],
            "imports": evidence["imports"][:15],
            "callees": [
                f"{c['callee_symbol']} in {c['callee_file']}" for c in evidence["callees"][:10]
            ],
            "callers": [
                f"{c['caller_symbol']} in {c['caller_file']}" for c in evidence["callers"][:10]
            ],
        }
        system = (
            "You are Synapse's engineering documentation author. Write concise, precise documentation. "
            "Synthesize a Behavioral Summary explaining runtime responsibilities and an Edge Cases & Gotchas section. "
            "Do not invent unevidenced facts. Return clean Markdown."
        )
        prompt = (
            f"Target: {evidence['path']}\n"
            "Task: Synthesize behavioral summary and gotchas for this file.\n"
            f"Evidence JSON:\n{json.dumps(prompt_evidence, indent=2)}"
        )
        try:
            response = self.provider.generate(
                system_prompt=system,
                user_prompt=prompt,
                max_tokens=600,
            )
            content = response.content.strip()
            return content if content else None
        except Exception as exc:
            logger.warning("wiki_llm_augmentation_failed", path=evidence["path"], error=str(exc))
            raise

    def _render_file_doc(self, evidence: dict[str, Any]) -> str:
        """Render documentation page, applying LLM augmentation when available."""
        llm_summary = self._augment_with_llm(evidence)
        return self._render_page(evidence, llm_summary=llm_summary)

    def _cleanup_orphans(self, current_source_paths: set[str]) -> list[str]:
        """Delete orphaned .md pages and remove empty directories under wiki_dir."""
        deleted: list[str] = []
        if not self.wiki_dir.exists():
            return deleted

        # Remove any synthetic category directories if they exist
        synthetic_dirs = ("architecture", "flows", "concepts", "integrations", "modules", "files")
        for syn_name in synthetic_dirs:
            syn_dir = self.wiki_dir / syn_name
            if syn_dir.is_dir():
                for sub in list(syn_dir.rglob("*")):
                    if sub.is_file():
                        sub.unlink(missing_ok=True)
                for sub_dir in sorted(syn_dir.glob("**/*"), reverse=True):
                    if sub_dir.is_dir():
                        try:
                            sub_dir.rmdir()
                        except OSError:
                            pass
                try:
                    syn_dir.rmdir()
                except OSError:
                    pass

        # Remove legacy synthetic root files if any
        synthetic_files = ("codebase-tree.md", "file-index.md")
        for syn_file in synthetic_files:
            syn_p = self.wiki_dir / syn_file
            if syn_p.is_file():
                syn_p.unlink(missing_ok=True)

        # Remove orphaned .md pages
        for md_path in list(self.wiki_dir.rglob("*.md")):
            rel_to_wiki = md_path.relative_to(self.wiki_dir).as_posix()
            source_rel_path = rel_to_wiki[:-3] if rel_to_wiki.endswith(".md") else rel_to_wiki
            if source_rel_path not in current_source_paths:
                try:
                    md_path.unlink(missing_ok=True)
                    deleted.append(rel_to_wiki)
                except OSError as exc:
                    logger.warning("wiki_orphan_unlink_failed", path=rel_to_wiki, error=str(exc))

        # Bottom-up removal of empty directories
        for dirpath in sorted(self.wiki_dir.glob("**/*"), reverse=True):
            if dirpath.is_dir() and dirpath != self.wiki_dir:
                try:
                    if not any(dirpath.iterdir()):
                        dirpath.rmdir()
                except OSError:
                    pass

        return deleted

    def generate(self, *, full: bool = False) -> dict[str, Any]:
        """
        Generate or incrementally update 1:1 documentation pages under .synap/wiki/.
        Never generates README files, index files, or synthetic categories.
        """
        paths = self._files()
        current_paths_set = set(paths)

        # Cleanup deleted or renamed files
        self._cleanup_orphans(current_paths_set)

        manifest = self._load_manifest() if not full else {}
        old_files = manifest.get("files", {})

        changed_items: list[tuple[str, str]] = []
        for p in paths:
            sha256 = self._compute_sha256(p)
            target_md = self.wiki_dir / f"{p}.md"
            # Must regenerate if full, target .md is missing, or hash changed
            if full or not target_md.exists() or old_files.get(p, {}).get("sha256") != sha256:
                changed_items.append((p, sha256))

        failures: list[str] = []
        new_files_manifest: dict[str, Any] = dict(old_files) if not full else {}

        # Remove deleted files from manifest
        for old_p in list(new_files_manifest.keys()):
            if old_p not in current_paths_set:
                new_files_manifest.pop(old_p, None)

        for p, sha256 in changed_items:
            try:
                evidence = self._evidence(p)
                doc = self._render_file_doc(evidence)
                target_md = self.wiki_dir / f"{p}.md"
                self._write_atomic(target_md, doc)
                new_files_manifest[p] = {
                    "sha256": sha256,
                    "lines": evidence["lines"],
                }
                self.store.set_wiki_status(p, evidence.get("git_oid"), "completed")
            except Exception as exc:
                failures.append(f"{p}: {exc}")
                logger.error("wiki_page_generation_failed", path=p, error=str(exc))

        git_state = GitRepository(self.settings.repository_path).state(force=True)
        head_commit = git_state.head_commit

        updated_manifest = {
            "repository_revision": head_commit,
            "branch": git_state.effective_branch,
            "generated_at": datetime.now(UTC).isoformat(),
            "generation_status": "failed" if failures else "complete",
            "files": new_files_manifest,
        }
        self._save_manifest(updated_manifest)

        if failures:
            raise RuntimeError("Wiki generation completed with failures:\n" + "\n".join(failures))

        return {
            "files": len(paths),
            "generated": len(changed_items),
            "revision": head_commit,
        }

    def status(self) -> dict[str, Any]:
        """Check whether wiki pages are fresh, stale, or missing."""
        paths = self._files()
        manifest = self._load_manifest()
        if not manifest or "files" not in manifest:
            return {"state": "missing", "files": len(paths), "stale": paths, "revision": None}

        stale: list[str] = []
        manifest_files = manifest.get("files", {})
        for p in paths:
            target_md = self.wiki_dir / f"{p}.md"
            if not target_md.exists():
                stale.append(p)
                continue
            if manifest_files.get(p, {}).get("sha256") != self._compute_sha256(p):
                stale.append(p)

        # Removed source files
        current_paths_set = set(paths)
        for old_p in manifest_files:
            if old_p not in current_paths_set:
                stale.append(old_p)

        git_state = GitRepository(self.settings.repository_path).state(force=True)
        return {
            "state": "stale" if stale else "fresh",
            "files": len(paths),
            "stale": sorted(set(stale)),
            "revision": git_state.head_commit,
        }

    def validate(self) -> list[str]:
        """Validate markdown fences and ensure all source files have 1:1 documentation pages."""
        errors: list[str] = []
        manifest = self._load_manifest()
        if not manifest:
            errors.append("missing .manifest.json")

        paths = self._files()
        for p in paths:
            target_md = self.wiki_dir / f"{p}.md"
            if not target_md.exists():
                errors.append(f"missing file documentation: {p}")

        for page in self.wiki_dir.rglob("*.md"):
            try:
                text = page.read_text(encoding="utf-8", errors="replace")
                if text.count("```") % 2 != 0:
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
            except OSError:
                pass

        return errors

    def ensure_wiki_page(self, wiki_filepath: str) -> None:
        """Ensure a single wiki page is generated and fresh."""
        source_path = self._resolve_source_path(wiki_filepath)
        abs_source = self.settings.repository_path / source_path
        if not abs_source.is_file():
            logger.warning("wiki_source_file_missing", path=source_path)
            return

        target_path = self.wiki_dir / f"{source_path}.md"
        current_sha = self._compute_sha256(source_path)
        manifest = self._load_manifest()

        if (
            target_path.exists()
            and manifest.get("files", {}).get(source_path, {}).get("sha256") == current_sha
        ):
            return

        evidence = self._evidence(source_path)
        doc = self._render_file_doc(evidence)
        self._write_atomic(target_path, doc)

        manifest.setdefault("files", {})[source_path] = {
            "sha256": current_sha,
            "lines": evidence["lines"],
        }
        self._save_manifest(manifest)
        self.store.set_wiki_status(source_path, evidence.get("git_oid"), "completed")
