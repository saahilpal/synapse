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

_BINARY_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".wasm",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".tar",
    ".gz",
    ".zip",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}

_LOCKFILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "cargo.lock",
    "composer.lock",
    "go.sum",
    "flake.lock",
    "uv.lock",
}

_MINIFIED_SUFFIXES = {
    ".min.js",
    ".min.css",
    ".map",
}

_PYTHON_BUILTINS = {
    "int",
    "str",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "bytes",
    "bytearray",
    "object",
    "type",
    "None",
    "True",
    "False",
    "Any",
    "Optional",
    "Union",
    "Callable",
    "Sequence",
    "Mapping",
    "Iterable",
    "Iterator",
    "Path",
    "Exception",
    "ValueError",
    "TypeError",
    "RuntimeError",
    "self",
    "cls",
}


def count_syllables(word: str) -> int:
    """Estimate syllable count for an English word."""
    cleaned = re.sub(r"[^a-z]", "", word.lower().strip())
    if not cleaned:
        return 0
    if len(cleaned) <= 3:
        return 1
    if cleaned.endswith("e") and not cleaned.endswith("le"):
        cleaned = cleaned[:-1]
    vowels = "aeiouy"
    count = len(re.findall(r"[aeiouy]+", cleaned))
    return max(1, count)


def flesch_kincaid_grade_level(text: str) -> float:
    """Calculate Flesch-Kincaid Grade Level for markdown prose."""
    clean = re.sub(r"```[\s\S]*?```", "", text)
    clean = re.sub(r"`[^`]*`", "", clean)
    clean = re.sub(r"#+[^\n]*", "", clean)
    clean = re.sub(r">.*", "", clean)
    clean = re.sub(r"\*\*[^*]+\*\*", "", clean)
    clean = re.sub(r"^\s*[-*0-9.]+\s+", "", clean, flags=re.MULTILINE)

    sentences = [s.strip() for s in re.split(r"[.!?]+", clean) if s.strip()]
    words = re.findall(r"\b[a-zA-Z]+\b", clean)
    if not sentences or not words or len(words) < 10:
        return 0.0

    total_words = len(words)
    total_sentences = len(sentences)
    total_syllables = sum(count_syllables(w) for w in words)

    fk = 0.39 * (total_words / total_sentences) + 11.8 * (total_syllables / total_words) - 15.59
    return round(fk, 2)


def redact_secrets(text: str) -> str:
    """Redact passwords, secret keys, tokens, and credentials from text."""
    redacted = re.sub(
        r"""(?i)(["']?(?:password|secret|token|api[_-]?key|access[_-]?key|auth|bearer|credential|private[_-]?key)["']?\s*[:=]\s*)(["']?)[^"'\s\n\r]{3,}(\2)""",
        r"\1\2[REDACTED]\2",
        text,
    )
    redacted = re.sub(
        r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,}\b",
        r"\1_[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]", redacted)
    redacted = re.sub(r"\bsk-[A-Za-z0-9]{20,}\b", "sk-[REDACTED]", redacted)
    redacted = re.sub(r"\bAIza[0-9A-Za-z\-_]{35}\b", "AIza[REDACTED]", redacted)
    redacted = re.sub(
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        redacted,
    )
    redacted = re.sub(
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "[REDACTED_JWT]",
        redacted,
    )
    return redacted


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
        self._init_db()

    def _init_db(self) -> None:
        """Initialize wiki_pages and wiki_pages_fts tables in SQLite."""
        try:
            with self.store.connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS wiki_pages (
                        path TEXT PRIMARY KEY,
                        title TEXT,
                        summary TEXT,
                        content TEXT,
                        file_type TEXT,
                        is_metadata INTEGER DEFAULT 0,
                        sha256 TEXT,
                        updated_at TEXT
                    )
                """)
                fts_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wiki_pages_fts'"
                ).fetchone()
                if not fts_exists:
                    conn.execute("""
                        CREATE VIRTUAL TABLE wiki_pages_fts USING fts5(
                            path,
                            title,
                            summary,
                            content
                        )
                    """)
        except Exception as exc:
            logger.warning("wiki_init_db_failed", error=str(exc))

    def _upsert_wiki_page_record(
        self,
        path: str,
        title: str,
        summary: str,
        content: str,
        file_type: str,
        is_metadata: bool,
        sha256: str,
    ) -> None:
        """Upsert documentation or metadata entry into wiki_pages and wiki_pages_fts."""
        now = datetime.now(UTC).isoformat()
        try:
            with self.store.connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO wiki_pages
                    (path, title, summary, content, file_type, is_metadata, sha256, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        path,
                        title,
                        summary,
                        content,
                        file_type,
                        1 if is_metadata else 0,
                        sha256,
                        now,
                    ),
                )
                conn.execute("DELETE FROM wiki_pages_fts WHERE path = ?", (path,))
                conn.execute(
                    """
                    INSERT INTO wiki_pages_fts (path, title, summary, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (path, title, summary, content),
                )
        except Exception as exc:
            logger.warning("wiki_upsert_record_failed", path=path, error=str(exc))

    def _delete_wiki_page_record(self, path: str) -> None:
        """Remove a page record from wiki_pages and wiki_pages_fts."""
        try:
            with self.store.connect() as conn:
                conn.execute("DELETE FROM wiki_pages WHERE path = ?", (path,))
                conn.execute("DELETE FROM wiki_pages_fts WHERE path = ?", (path,))
        except Exception as exc:
            logger.warning("wiki_delete_record_failed", path=path, error=str(exc))

    def search_wiki(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search plain-English wiki pages using SQLite FTS5."""
        clean_tokens = [t for t in re.sub(r"[^\w\s]", " ", query).split() if t]
        if not clean_tokens:
            return []
        fts_query = " OR ".join(clean_tokens)
        try:
            with self.store.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT path, title, summary, content, bm25(wiki_pages_fts) as rank
                    FROM wiki_pages_fts
                    WHERE wiki_pages_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("wiki_search_failed", query=query, error=str(exc))
            return []

    def get_folder_summary(self, dir_path: str) -> str:
        """Render folder summary on demand from database rows."""
        clean_dir = dir_path.strip("/.")
        prefix = f"{clean_dir}/" if clean_dir else ""
        try:
            with self.store.connect() as conn:
                if clean_dir:
                    rows = conn.execute(
                        """
                        SELECT path, title, summary, file_type, is_metadata
                        FROM wiki_pages
                        WHERE path LIKE ?
                        ORDER BY path
                        """,
                        (f"{prefix}%",),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT path, title, summary, file_type, is_metadata FROM wiki_pages ORDER BY path"
                    ).fetchall()
            items = [dict(r) for r in rows]
        except Exception:
            items = []

        if not items:
            return f"# Folder: {dir_path}\n\nNo documented files recorded in this folder.\n"

        lines = [f"# Folder: {dir_path or 'root'}", ""]
        lines.append(f"Contains {len(items)} tracked files and modules.")
        lines.append("")
        lines.append("## Files")
        for it in items:
            p = it["path"]
            s = it["summary"] or "No summary available."
            meta_tag = " (metadata only)" if it.get("is_metadata") else ""
            lines.append(f"- `{p}`{meta_tag}: {s}")
        lines.append("")
        return "\n".join(lines)

    def generate_file_wiki(self, file_id: str, file_path: str, content: str) -> None:
        """Enqueue file for background wiki generation."""
        self.store.enqueue_wiki(file_path)

    def generate_file_wiki_sync(self, file_path: str, content: str, git_oid: str) -> None:
        """Synchronously generate or update a single file wiki page."""
        self.ensure_wiki_page(file_path)

    def generate_module_wiki(self, dir_path: str) -> None:
        """Folder summaries live in the database and render on demand."""
        summary = self.get_folder_summary(dir_path)
        self._upsert_wiki_page_record(
            path=dir_path or "root",
            title=f"Folder: {dir_path or 'root'}",
            summary=f"Folder summary for {dir_path or 'root'}.",
            content=summary,
            file_type="directory",
            is_metadata=False,
            sha256="",
        )

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

    def _classify_file(self, rel_path: str, abs_path: Path) -> str:
        """Categorize file into a type-specific group."""
        name_lower = abs_path.name.lower()
        suffix = abs_path.suffix.lower()

        # Binary, image, lockfile, minified, generated -> metadata only
        if suffix in _BINARY_SUFFIXES or _is_binary_file(abs_path):
            return "metadata"
        if name_lower in _LOCKFILE_NAMES or suffix == ".lock":
            return "metadata"
        if suffix in _MINIFIED_SUFFIXES or ".min." in name_lower:
            return "metadata"
        if (
            ".generated." in name_lower
            or name_lower.endswith("_pb2.py")
            or name_lower.endswith(".pb.go")
        ):
            return "metadata"

        # Tests
        path_slash = f"/{rel_path}"
        if (
            "/tests/" in path_slash
            or "/test/" in path_slash
            or "/spec/" in path_slash
            or name_lower.startswith("test_")
            or name_lower.endswith("_test.py")
            or name_lower.endswith(".test.ts")
            or name_lower.endswith(".test.js")
            or name_lower.endswith(".spec.ts")
            or name_lower.endswith(".spec.js")
            or name_lower.endswith("_test.go")
        ):
            return "test"

        # Data, SQL, migrations, schemas
        if (
            suffix in {".sql", ".prisma", ".graphql", ".gql", ".proto"}
            or "migration" in rel_path.lower()
        ):
            return "data_schema"

        # Config & build
        if (
            suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml"}
            or name_lower
            in {
                "dockerfile",
                "makefile",
                "containerfile",
                "procfile",
                ".env.example",
                ".env",
                ".gitignore",
                ".dockerignore",
                ".editorconfig",
                ".gitattributes",
                "tox.ini",
                "tsconfig.json",
                "pyproject.toml",
                "cargo.toml",
                "package.json",
            }
            or "/.github/" in path_slash
            or rel_path.startswith(".github/")
        ):
            return "config_build"

        # Docs & text
        if suffix in {".md", ".rst", ".txt", ".adoc"}:
            return "docs_text"

        # Scripts, templates, HTML/CSS, notebooks
        if suffix in {
            ".sh",
            ".bash",
            ".zsh",
            ".html",
            ".htm",
            ".css",
            ".scss",
            ".sass",
            ".less",
            ".ipynb",
            ".jinja",
            ".j2",
        }:
            return "scripts_templates"

        # Default to source code
        return "source_code"

    def _files(self) -> list[str]:
        """Return tracked and non-ignored paths, deterministically sorted."""
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
            abs_p = root / path_obj
            if not abs_p.is_file():
                continue
            filtered.append(str_path)

        return sorted(set(filtered))

    def _extract_git_log(self, rel_path: str) -> list[str]:
        """Extract recent commit history lines for the file."""
        root = self.settings.repository_path.resolve()
        try:
            res = subprocess.run(
                ["git", "log", "-n", "5", "--oneline", "--", rel_path],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    def _extract_module_docstring(self, content: str) -> str | None:
        """Extract module-level docstring from Python code."""
        try:
            parsed_ast = ast.parse(content)
            return ast.get_docstring(parsed_ast)
        except Exception:
            return None

    def _extract_leading_comment(self, content: str) -> str | None:
        """Extract leading comment block as purpose fallback."""
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
        return " ".join(comment_lines).strip() if comment_lines else None

    def _extract_facts(self, path: str, all_repo_paths: set[str]) -> dict[str, Any]:
        """Extract deterministic facts using type-specific extractors."""
        abs_path = self.settings.repository_path / path
        file_type = self._classify_file(path, abs_path)

        # 1. Metadata-only files (binary, lockfile, minified, generated)
        if file_type == "metadata":
            try:
                size_bytes = abs_path.stat().st_size
            except OSError:
                size_bytes = 0
            if abs_path.suffix.lower() in _BINARY_SUFFIXES or _is_binary_file(abs_path):
                desc = f"Binary asset ({size_bytes} bytes)."
            elif abs_path.name.lower() in _LOCKFILE_NAMES or abs_path.suffix.lower() == ".lock":
                desc = "Lockfile recording resolved dependency versions and hashes."
            elif abs_path.suffix.lower() in _MINIFIED_SUFFIXES:
                desc = f"Minified code asset ({size_bytes} bytes)."
            else:
                desc = f"Generated code asset ({size_bytes} bytes)."
            return {
                "path": path,
                "file_type": "metadata",
                "is_metadata": True,
                "what_it_does": desc,
                "summary": desc,
                "how_it_works": [],
                "key_parts": [],
                "connects_to": [],
                "watch_out_for": "Do not edit directly; regenerated during build.",
                "recent_changes": [],
                "all_known_symbols": set(),
                "all_repo_paths": all_repo_paths,
            }

        content = abs_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        git_log = self._extract_git_log(path)
        all_known_symbols: set[str] = set()

        file_entry = self.store.get_file_by_path(path)
        file_id = file_entry["file_id"] if file_entry else None

        # Callers & Callees from store
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
                        LIMIT 30
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
                        LIMIT 30
                        """,
                        (file_id,),
                    ).fetchall()
                    callers = [dict(r) for r in caller_rows]
            except Exception as exc:
                logger.warning("wiki_facts_edge_query_failed", path=path, error=str(exc))

        # Architectural decisions impacting this file
        decisions: list[str] = []
        try:
            with self.store.connect() as conn:
                d_rows = conn.execute(
                    """
                    SELECT content FROM decisions
                    WHERE context LIKE ? OR content LIKE ?
                    ORDER BY created_at DESC LIMIT 5
                    """,
                    (f"%{path}%", f"%{path}%"),
                ).fetchall()
                decisions = [str(r["content"]) for r in d_rows]
        except Exception:
            pass

        # 2. Config & Build Extractor
        if file_type == "config_build":
            redacted_content = redact_secrets(content)
            config_keys: list[tuple[str, str]] = []
            what_it_does = f"Configures settings and build options for `{path}`."
            if path == ".env.example" or path.endswith(".env"):
                what_it_does = "Sample settings file for app options."
                for line in redacted_content.splitlines():
                    trimmed = line.strip()
                    if trimmed and not trimmed.startswith("#") and "=" in trimmed:
                        k, _ = trimmed.split("=", 1)
                        config_keys.append((k.strip(), f"Sets {k.strip()} option."))
            elif path.endswith(".gitignore"):
                what_it_does = "Tells git which files and folders to ignore."
                for line in redacted_content.splitlines():
                    trimmed = line.strip()
                    if trimmed and not trimmed.startswith("#"):
                        config_keys.append((trimmed, f"Ignores path {trimmed}."))
            elif path.endswith(".json"):
                try:
                    obj = json.loads(redacted_content)
                    if isinstance(obj, dict):
                        for k in list(obj.keys())[:15]:
                            config_keys.append((k, f"Top-level config section for {k}."))
                except Exception:
                    pass
            elif path.endswith(".toml") or path.endswith(".ini") or path.endswith(".cfg"):
                for line in redacted_content.splitlines():
                    match = re.match(r"^\s*(\[[\w.-]+\]|[\w.-]+\s*=)", line)
                    if match:
                        raw_k = match.group(1).strip("[] =")
                        config_keys.append((raw_k, f"Sets {raw_k} setting."))
            elif "Dockerfile" in path:
                what_it_does = "Defines container image build steps and runtime environment."
                for line in redacted_content.splitlines():
                    if re.match(r"^(FROM|RUN|CMD|ENTRYPOINT|EXPOSE|ENV)\s", line):
                        cmd = line.split()[0]
                        config_keys.append((cmd, f"Executes container {cmd} instruction."))
            elif "Makefile" in path:
                what_it_does = "Provides build targets and automation recipes for make."
                for line in redacted_content.splitlines():
                    m = re.match(r"^([\w.-]+):", line)
                    if m:
                        target = m.group(1)
                        config_keys.append((target, f"Build recipe target for {target}."))

            for k, _ in config_keys:
                all_known_symbols.add(k)

            watch_out = "Changes here can break startup. Check that required keys stay set."
            return {
                "path": path,
                "file_type": "config_build",
                "is_metadata": False,
                "what_it_does": what_it_does,
                "summary": what_it_does,
                "how_it_works": [
                    "Reads settings and environment variables.",
                    "Sets runtime options for the system.",
                ],
                "key_parts": config_keys[:20],
                "connects_to": [f"`{p}`" for p in all_repo_paths if "config" in p and p != path][
                    :5
                ],
                "watch_out_for": watch_out,
                "recent_changes": git_log,
                "all_known_symbols": all_known_symbols,
                "all_repo_paths": all_repo_paths,
            }

        # 3. Docs & Text Extractor
        if file_type == "docs_text":
            headings: list[str] = []
            for line in lines:
                h_match = re.match(r"^#+\s+(.+)$", line)
                if h_match:
                    headings.append(h_match.group(1).strip())
            title = headings[0] if headings else path
            what_it_does = (
                f"Documentation file explaining {title}. Intended for developers and users."
            )
            key_parts = [(h, "Document section header.") for h in headings[1:10]]
            for h in headings:
                all_known_symbols.add(h)
            linked_paths = [p for p in all_repo_paths if p in content and p != path]
            return {
                "path": path,
                "file_type": "docs_text",
                "is_metadata": False,
                "what_it_does": what_it_does,
                "summary": what_it_does,
                "how_it_works": [
                    "Outlines architecture conventions and operational guidelines.",
                    "Provides code examples and reference workflows.",
                ],
                "key_parts": key_parts,
                "connects_to": [f"`{p}`" for p in linked_paths[:5]],
                "watch_out_for": "Keep documentation synchronized when updating related code.",
                "recent_changes": git_log,
                "all_known_symbols": all_known_symbols,
                "all_repo_paths": all_repo_paths,
            }

        # 4. Data, SQL, Schemas Extractor
        if file_type == "data_schema":
            tables: list[str] = []
            for line in lines:
                t_match = re.search(
                    r"(?i)create\s+table\s+(?:if\s+not\s+exists\s+)?([`\"\w]+)", line
                )
                if t_match:
                    tables.append(t_match.group(1).strip('`"'))
            what_it_does = f"Defines database schema tables and storage structures for `{path}`."
            key_parts = [(tbl, f"Database table `{tbl}`.") for tbl in tables]
            for t in tables:
                all_known_symbols.add(t)
            return {
                "path": path,
                "file_type": "data_schema",
                "is_metadata": False,
                "what_it_does": what_it_does,
                "summary": what_it_does,
                "how_it_works": [
                    "Creates persistent tables and defines column types.",
                    "Enforces indices, primary keys, and relational constraints.",
                ],
                "key_parts": key_parts,
                "connects_to": [
                    f"`{p}`" for p in all_repo_paths if "sqlite" in p or "storage" in p
                ][:5],
                "watch_out_for": "Modifying tables requires migration scripts to prevent data loss.",
                "recent_changes": git_log,
                "all_known_symbols": all_known_symbols,
                "all_repo_paths": all_repo_paths,
            }

        # 5. Tests Extractor
        if file_type == "test":
            test_funcs: list[str] = []
            for line in lines:
                m = re.match(r"^\s*def\s+(test_[\w]+)", line)
                if m:
                    test_funcs.append(m.group(1))
            what_it_does = (
                f"Runs automated tests verifying behavior and contract requirements for `{path}`."
            )
            key_parts = [(fn, "Test case verifying expected behavior.") for fn in test_funcs]
            for fn in test_funcs:
                all_known_symbols.add(fn)
            tested_modules = [
                p
                for p in all_repo_paths
                if p in content and p != path and not p.startswith("tests/")
            ]
            return {
                "path": path,
                "file_type": "test",
                "is_metadata": False,
                "what_it_does": what_it_does,
                "summary": what_it_does,
                "how_it_works": [
                    "Sets up test fixtures and required mocks.",
                    "Executes test scenarios against target functions and classes.",
                    "Asserts expected outcomes and error handling.",
                ],
                "key_parts": key_parts[:20],
                "connects_to": [f"`{p}`" for p in tested_modules[:5]],
                "watch_out_for": "Tests mock external services; end-to-end network errors may not be covered.",
                "recent_changes": git_log,
                "all_known_symbols": all_known_symbols,
                "all_repo_paths": all_repo_paths,
            }

        # 6. Scripts & Templates Extractor
        if file_type == "scripts_templates":
            what_it_does = f"Script or template automating tasks in `{path}`."
            cmd_steps: list[str] = []
            for line in lines:
                s_line = line.strip()
                if s_line and not s_line.startswith("#"):
                    cmd_steps.append(s_line[:60])
            return {
                "path": path,
                "file_type": "scripts_templates",
                "is_metadata": False,
                "what_it_does": what_it_does,
                "summary": what_it_does,
                "how_it_works": [
                    "Parses command line arguments and environment variables.",
                    "Executes automated task pipeline.",
                ],
                "key_parts": [(cmd_steps[0], "Primary command step.")] if cmd_steps else [],
                "connects_to": [],
                "watch_out_for": "Ensure required interpreter and environment dependencies are installed.",
                "recent_changes": git_log,
                "all_known_symbols": all_known_symbols,
                "all_repo_paths": all_repo_paths,
            }

        # 7. Source Code Extractor (Python, JS, TS, Go, Rust, etc.)
        raw_lang = file_entry.get("language") if file_entry else None
        language = str(raw_lang) if raw_lang else (abs_path.suffix.lstrip(".") or "unknown")

        module_doc = (
            self._extract_module_docstring(content)
            if language == "python"
            else self._extract_leading_comment(content)
        )

        symbols: list[dict[str, Any]] = []
        if file_id:
            symbols = self.store.get_symbols_by_file(file_id)
        if not symbols:
            try:
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
            except Exception:
                pass

        symbol_docstrings: dict[str, str] = {}
        if language == "python":
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                        ds = ast.get_docstring(node)
                        if ds:
                            symbol_docstrings[node.name] = ds.splitlines()[0].strip()
            except Exception:
                pass

        public_parts: list[tuple[str, str]] = []
        for s in symbols:
            name = s["name"]
            all_known_symbols.add(name)
            if name.startswith("_") and not name.startswith("__init__"):
                continue
            summary = (
                symbol_docstrings.get(name) or f"Public {s['kind'].replace('_definition', '')}."
            )
            public_parts.append((name, summary))

        if module_doc:
            clean_doc = " ".join(module_doc.splitlines()).strip()
            what_it_does = clean_doc
        elif public_parts:
            primary_names = ", ".join(f"`{p[0]}`" for p in public_parts[:3])
            what_it_does = f"Source code implementing {primary_names} for `{path}`."
        else:
            what_it_does = f"Source code module for `{path}`."

        connects_list: list[str] = []
        direct_imports = [
            line.strip()
            for line in lines
            if re.match(r"^(import |from |require\(|#include |use |export )", line.strip())
        ]
        for imp in direct_imports[:5]:
            connects_list.append(f"Imports `{imp}`")
        for cl in callers[:3]:
            connects_list.append(f"Used by `{cl['caller_file']}` via `{cl['caller_symbol']}`")
        for ca in callees[:3]:
            connects_list.append(f"Calls `{ca['callee_symbol']}` in `{ca['callee_file']}`")

        watch_out = (
            decisions[0] if decisions else "Check caller files before changing function names."
        )

        return {
            "path": path,
            "file_type": "source_code",
            "is_metadata": False,
            "what_it_does": what_it_does,
            "summary": what_it_does,
            "how_it_works": [
                "Imports needed files and helper tools.",
                "Runs code through public functions and classes.",
                "Sends back results to callers.",
            ],
            "key_parts": public_parts[:20],
            "connects_to": connects_list,
            "watch_out_for": watch_out,
            "recent_changes": git_log,
            "all_known_symbols": all_known_symbols,
            "all_repo_paths": all_repo_paths,
        }

    def _render_skeleton(self, facts: dict[str, Any]) -> str:
        """Render facts-only skeleton following the fixed template."""
        path = facts["path"]
        parts: list[str] = [
            f"# {path}",
            "",
            "> *Note: Auto-extracted structural skeleton, no LLM summary.*",
            "",
            f"**What it does:** {facts['what_it_does']}",
            "",
        ]

        if facts["how_it_works"]:
            parts.append("**How it works**")
            for i, step in enumerate(facts["how_it_works"], 1):
                clean_step = step if re.match(r"^\d+\.", step) else f"{i}. {step}"
                parts.append(clean_step)
            parts.append("")

        if facts["key_parts"]:
            parts.append("**Key parts**")
            for sym, desc in facts["key_parts"]:
                parts.append(f"- `{sym}`: {desc}")
            parts.append("")

        if facts["connects_to"]:
            parts.append("**Connects to:**")
            for conn in facts["connects_to"]:
                clean_conn = conn if conn.startswith("- ") else f"- {conn}"
                parts.append(clean_conn)
            parts.append("")

        if facts["watch_out_for"]:
            parts.append(f"**Watch out for:** {facts['watch_out_for']}")
            parts.append("")

        if facts["recent_changes"]:
            parts.append("**Recent changes:**")
            for ch in facts["recent_changes"][:5]:
                clean_ch = ch if ch.startswith("- ") else f"- {ch}"
                parts.append(clean_ch)
            parts.append("")

        return "\n".join(parts) + "\n"

    def _validate_page(self, text: str, facts: dict[str, Any]) -> list[str]:
        """Validate generated wiki page for accuracy, completeness, and reading level."""
        errors: list[str] = []

        # 1. Balanced fences
        if text.count("```") % 2 != 0:
            errors.append("Unbalanced markdown fences.")

        # 2. No empty sections
        headers = [
            r"\*\*What it does:\*\*",
            r"\*\*How it works\*\*",
            r"\*\*Key parts\*\*",
            r"\*\*Connects to:\*\*",
            r"\*\*Watch out for:\*\*",
            r"\*\*Recent changes:\*\*",
        ]
        pattern = "(" + "|".join(headers) + ")"
        matches = list(re.finditer(pattern, text))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_content = text[start:end].strip()
            if not section_content:
                errors.append(f"Empty section under {m.group(1)}.")

        # 3. Reading level <= 8.5
        fkgl = flesch_kincaid_grade_level(text)
        if fkgl > 8.5:
            errors.append(f"Reading level too high: {fkgl} > 8.5.")

        # 4. Verified symbols and paths
        code_spans = re.findall(r"`([^`]+)`", text)
        known_symbols = facts["all_known_symbols"] | _PYTHON_BUILTINS
        known_paths = facts["all_repo_paths"]

        for span in code_spans:
            token = span.strip()
            if not token or len(token) <= 1:
                continue
            clean_token = token.rstrip("()")
            if (
                clean_token in known_symbols
                or clean_token in known_paths
                or any(clean_token in p for p in known_paths)
                or any(p.endswith(clean_token) for p in known_paths)
                or clean_token in {"python", "bash", "json", "yaml", "toml", "sql", "git"}
            ):
                continue
            if " " in token or "=" in token or ":" in token:
                continue
            errors.append(f"Unevidenced symbol or path: `{token}`.")

        return errors

    def _synthesize_with_llm(self, facts: dict[str, Any]) -> str:
        """Synthesize plain-English wiki documentation with local LLM and validation."""
        if self.provider is None:
            return self._render_skeleton(facts)

        system = (
            "You are Synapse's engineering documentation author. Write concise, plain English documentation. "
            "Target an 8th-grade reading level (Flesch-Kincaid <= 8.5) using short sentences and active voice. "
            "Define technical terms first time. Do not use filler ('This file is responsible for') or marketing words. "
            "Only reference symbols and file paths provided in the extracted facts. Omit empty sections. "
            "Follow this template strictly:\n"
            "# <path>\n"
            "**What it does:** <1-3 plain sentences>\n"
            "**How it works**\n"
            "1. ...\n"
            "**Key parts**\n"
            "- `<symbol>`: <one-line summary>\n"
            "**Connects to:** <links to related files / dependencies>\n"
            "**Watch out for:** <gotchas, breaking changes>\n"
            "**Recent changes:** <one line each from git log>\n"
        )

        user_prompt = (
            f"Target: {facts['path']}\n"
            f"File Type: {facts['file_type']}\n"
            f"Facts JSON:\n{json.dumps({k: v for k, v in facts.items() if k not in {'all_known_symbols', 'all_repo_paths'}}, default=str, indent=2)}"
        )

        try:
            resp = self.provider.generate(
                system_prompt=system, user_prompt=user_prompt, max_tokens=600
            )
        except Exception as exc:
            logger.warning("wiki_llm_synthesis_failed", path=facts["path"], error=str(exc))
            raise

        candidate = resp.content.strip()
        if not candidate.startswith("#"):
            candidate = f"# {facts['path']}\n\n**What it does:** {candidate}\n"

        errors = self._validate_page(candidate, facts)
        if not errors:
            return candidate + "\n"

        # Regenerate once with feedback
        logger.info("wiki_llm_validation_failed_retrying", path=facts["path"], errors=errors)
        fix_prompt = (
            f"{user_prompt}\n\n"
            f"Your previous attempt had validation errors:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\nPlease fix these issues: keep sentences short, reading level under 8.5, "
            "omit empty sections, and only name symbols present in the facts."
        )
        try:
            resp2 = self.provider.generate(
                system_prompt=system, user_prompt=fix_prompt, max_tokens=600
            )
            candidate2 = resp2.content.strip()
            if not candidate2.startswith("#"):
                candidate2 = f"# {facts['path']}\n\n**What it does:** {candidate2}\n"
            errors2 = self._validate_page(candidate2, facts)
            if not errors2:
                return candidate2 + "\n"
            logger.warning(
                "wiki_llm_regeneration_failed_falling_back", path=facts["path"], errors=errors2
            )
            return self._render_skeleton(facts)
        except Exception as exc2:
            logger.warning(
                "wiki_llm_retry_failed_falling_back", path=facts["path"], error=str(exc2)
            )
            return self._render_skeleton(facts)

    def _cleanup_orphans(
        self, current_source_paths: set[str], metadata_paths: set[str]
    ) -> list[str]:
        """Delete orphaned .md pages, remove empty directories, and sync database."""
        deleted: list[str] = []
        if not self.wiki_dir.exists():
            return deleted

        # Remove synthetic categories if any
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

        # Remove synthetic root files if any
        for syn_file in ("codebase-tree.md", "file-index.md", "README.md"):
            syn_p = self.wiki_dir / syn_file
            if syn_p.is_file():
                syn_p.unlink(missing_ok=True)

        # Remove orphaned .md pages (and pages that are now metadata-only)
        for md_path in list(self.wiki_dir.rglob("*.md")):
            rel_to_wiki = md_path.relative_to(self.wiki_dir).as_posix()
            source_rel_path = rel_to_wiki[:-3] if rel_to_wiki.endswith(".md") else rel_to_wiki
            if source_rel_path not in current_source_paths or source_rel_path in metadata_paths:
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

        # Cleanup deleted files from SQLite tables
        try:
            with self.store.connect() as conn:
                rows = conn.execute("SELECT path FROM wiki_pages").fetchall()
                for r in rows:
                    p = str(r["path"])
                    if p not in current_source_paths and not p.startswith("Folder:"):
                        self._delete_wiki_page_record(p)
        except Exception:
            pass

        return deleted

    def generate(self, *, full: bool = False) -> dict[str, Any]:
        """
        Generate or incrementally update 1:1 documentation pages under .synap/wiki/.
        Every tracked file gets documented using a type-specific extractor.
        Binary, image, lockfile, minified, and generated files record a 1-line metadata
        entry in SQLite wiki_pages and do NOT create a markdown file.
        """
        paths = self._files()
        current_paths_set = set(paths)
        root = self.settings.repository_path.resolve()

        metadata_paths: set[str] = set()
        for p in paths:
            abs_p = root / p
            if self._classify_file(p, abs_p) == "metadata":
                metadata_paths.add(p)

        # Cleanup deleted or renamed files
        self._cleanup_orphans(current_paths_set, metadata_paths)

        manifest = self._load_manifest() if not full else {}
        old_files = manifest.get("files", {})

        changed_items: list[tuple[str, str, bool]] = []
        for p in paths:
            sha256 = self._compute_sha256(p)
            is_meta = p in metadata_paths
            target_md = self.wiki_dir / f"{p}.md"
            # Needs update if full, target .md missing (for non-metadata), or hash changed
            if (
                full
                or (not is_meta and not target_md.exists())
                or old_files.get(p, {}).get("sha256") != sha256
            ):
                changed_items.append((p, sha256, is_meta))

        failures: list[str] = []
        new_files_manifest: dict[str, Any] = dict(old_files) if not full else {}

        # Remove deleted files from manifest
        for old_p in list(new_files_manifest.keys()):
            if old_p not in current_paths_set:
                new_files_manifest.pop(old_p, None)

        for p, sha256, is_meta in changed_items:
            try:
                facts = self._extract_facts(p, current_paths_set)
                if is_meta:
                    self._upsert_wiki_page_record(
                        path=p,
                        title=Path(p).name,
                        summary=facts["summary"],
                        content=facts["what_it_does"],
                        file_type=facts["file_type"],
                        is_metadata=True,
                        sha256=sha256,
                    )
                    target_md = self.wiki_dir / f"{p}.md"
                    if target_md.exists():
                        target_md.unlink(missing_ok=True)
                else:
                    doc = self._synthesize_with_llm(facts)
                    target_md = self.wiki_dir / f"{p}.md"
                    self._write_atomic(target_md, doc)
                    self._upsert_wiki_page_record(
                        path=p,
                        title=Path(p).name,
                        summary=facts["summary"],
                        content=doc,
                        file_type=facts["file_type"],
                        is_metadata=False,
                        sha256=sha256,
                    )

                new_files_manifest[p] = {
                    "sha256": sha256,
                    "is_metadata": is_meta,
                }
                self.store.set_wiki_status(p, None, "completed")
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
        """Check whether wiki documentation pages and metadata entries are fresh or stale."""
        paths = self._files()
        manifest = self._load_manifest()
        if not manifest or "files" not in manifest:
            return {"state": "missing", "files": len(paths), "stale": paths, "revision": None}

        root = self.settings.repository_path.resolve()
        stale: list[str] = []
        manifest_files = manifest.get("files", {})

        for p in paths:
            abs_p = root / p
            is_meta = self._classify_file(p, abs_p) == "metadata"
            target_md = self.wiki_dir / f"{p}.md"
            if not is_meta and not target_md.exists():
                stale.append(p)
                continue
            if manifest_files.get(p, {}).get("sha256") != self._compute_sha256(p):
                stale.append(p)

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
        """Validate documentation completeness, balanced fences, and absence of empty sections."""
        errors: list[str] = []
        manifest = self._load_manifest()
        if not manifest:
            errors.append("missing .manifest.json")

        paths = self._files()
        root = self.settings.repository_path.resolve()

        for p in paths:
            abs_p = root / p
            is_meta = self._classify_file(p, abs_p) == "metadata"
            target_md = self.wiki_dir / f"{p}.md"
            if is_meta and target_md.exists():
                errors.append(f"metadata-only file should not have a markdown page: {p}")
            elif not is_meta and not target_md.exists():
                errors.append(f"missing file documentation: {p}")

        for page in self.wiki_dir.rglob("*.md"):
            try:
                text = page.read_text(encoding="utf-8", errors="replace")
                if text.count("```") % 2 != 0:
                    errors.append(f"unbalanced Markdown fences: {page.relative_to(self.wiki_dir)}")
                fkgl = flesch_kincaid_grade_level(text)
                if fkgl > 8.5:
                    errors.append(
                        f"reading level exceeds 8.5 ({fkgl}): {page.relative_to(self.wiki_dir)}"
                    )
            except OSError:
                pass

        return errors

    def ensure_wiki_page(self, wiki_filepath: str) -> None:
        """Ensure a single wiki page or metadata entry is generated and fresh."""
        source_path = self._resolve_source_path(wiki_filepath)
        abs_source = self.settings.repository_path / source_path
        if not abs_source.is_file():
            logger.warning("wiki_source_file_missing", path=source_path)
            return

        current_sha = self._compute_sha256(source_path)
        manifest = self._load_manifest()
        is_meta = self._classify_file(source_path, abs_source) == "metadata"
        target_path = self.wiki_dir / f"{source_path}.md"

        if (is_meta or target_path.exists()) and manifest.get("files", {}).get(source_path, {}).get(
            "sha256"
        ) == current_sha:
            return

        all_paths = set(self._files())
        facts = self._extract_facts(source_path, all_paths)

        if is_meta:
            self._upsert_wiki_page_record(
                path=source_path,
                title=abs_source.name,
                summary=facts["summary"],
                content=facts["what_it_does"],
                file_type=facts["file_type"],
                is_metadata=True,
                sha256=current_sha,
            )
            if target_path.exists():
                target_path.unlink(missing_ok=True)
        else:
            doc = self._synthesize_with_llm(facts)
            self._write_atomic(target_path, doc)
            self._upsert_wiki_page_record(
                path=source_path,
                title=abs_source.name,
                summary=facts["summary"],
                content=doc,
                file_type=facts["file_type"],
                is_metadata=False,
                sha256=current_sha,
            )

        manifest.setdefault("files", {})[source_path] = {
            "sha256": current_sha,
            "is_metadata": is_meta,
        }
        self._save_manifest(manifest)
        self.store.set_wiki_status(source_path, None, "completed")
