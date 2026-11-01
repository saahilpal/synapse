from __future__ import annotations

import contextlib
import hashlib
import json
import multiprocessing
import subprocess
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any

import structlog
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from synap_git.config import SynapSettings
from synap_git.diagnostics.logger import get_logger
from synap_git.diagnostics.tracing import TraceStore
from synap_git.git import GitRepository, GitState
from synap_git.indexer.scanner import RepositoryScanner, _is_binary_file
from synap_git.indexer.wiki import WikiEngine
from synap_git.parser.registry import CodeParserRegistry
from synap_git.provider.factory import get_embed_provider, get_llm_provider
from synap_git.retrieval.engine import HybridRetrievalEngine
from synap_git.storage.sqlite import SynapStore
from synap_git.utils.serialization import stable_hash

STDLIB_MODULES: set[str] = {
    # Python
    "abc",
    "argparse",
    "ast",
    "asyncio",
    "base64",
    "collections",
    "contextlib",
    "copy",
    "csv",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "glob",
    "hashlib",
    "io",
    "itertools",
    "json",
    "logging",
    "math",
    "multiprocessing",
    "operator",
    "os",
    "pathlib",
    "pickle",
    "random",
    "re",
    "shutil",
    "signal",
    "socket",
    "sqlite3",
    "string",
    "struct",
    "subprocess",
    "sys",
    "tempfile",
    "threading",
    "time",
    "traceback",
    "types",
    "typing",
    "typing_extensions",
    "unittest",
    "urllib",
    "uuid",
    "warnings",
    "weakref",
    "pydantic",
    "pytest",
    "structlog",
    # JS / TS / Node
    "node",
    "fs",
    "path",
    "http",
    "https",
    "url",
    "crypto",
    "events",
    "stream",
    "util",
    "child_process",
    "assert",
    "buffer",
    "process",
    "react",
    "react-dom",
    "next",
    # Go
    "bufio",
    "bytes",
    "context",
    "encoding",
    "errors",
    "flag",
    "fmt",
    "log",
    "net",
    "reflect",
    "regexp",
    "sort",
    "strconv",
    "strings",
    "sync",
    "syscall",
    "testing",  # Rust
    "std",
    "core",
    "alloc",
    # Java
    "java",
    "javax",
    "org.junit",
    # C/C++
    "iostream",
    "vector",
    "stdio.h",
    "stdlib.h",
    "string.h",
    "memory",
    "map",
    "set",
    "algorithm",
    "cmath",
    "thread",
    "chrono",
    "cstdio",
    "cstdlib",
}


def _is_stdlib_module(mod: str) -> bool:
    if mod.startswith("node:") or (mod.startswith("<") and mod.endswith(">")):
        return True
    root = mod.split(":")[0].split(".")[0].split("::")[0].split("/")[0]
    return root in STDLIB_MODULES or mod in STDLIB_MODULES


def _parse_worker(args: tuple[Path, str]) -> dict[str, Any]:
    path, rel_path = args
    registry = CodeParserRegistry()
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = ""
    res = registry.parse(path, relative_path=rel_path, text=content)
    return {
        "path": res.path,
        "language": res.language,
        "symbols": [
            {
                "symbol_id": sym.stable_id,
                "name": sym.name,
                "kind": sym.kind,
                "start_line": sym.start_line,
                "end_line": sym.end_line,
                "ast_hash": sym.ast_hash,
                "metadata": sym.metadata,
            }
            for sym in res.symbols
        ],
        "imports": list(res.imports),
        "syntax_error": res.syntax_error,
    }


@dataclass(frozen=True)
class RuntimeStatus:
    repository_path: str
    branch: str
    git_commit: str | None
    active_commit: str | None
    symbols: int
    files: int
    mode: str
    is_dirty: bool = False


def _generate_candidate_paths(current_rel_path: str, module_part: str) -> list[str]:
    candidates: list[str] = []
    current_path = Path(current_rel_path)
    exts = [
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".cpp",
        ".cc",
        ".c",
        ".h",
        ".hpp",
        ".rb",
        ".cs",
        ".php",
        ".kt",
        ".scala",
    ]

    # Handle relative imports starting with .
    if module_part.startswith("."):
        if module_part.startswith(("./", "../")):
            try:
                base_dir = current_path.parent
                cand_path = Path(module_part)
                norm_parts = list(base_dir.parts)
                for part in cand_path.parts:
                    if part in (".", ""):
                        continue
                    elif part == "..":
                        if norm_parts:
                            norm_parts.pop()
                    else:
                        norm_parts.append(part)
                cand_base = "/".join(norm_parts)
                if cand_base:
                    candidates.append(cand_base)
                    for ext in exts:
                        candidates.append(f"{cand_base}{ext}")
                        candidates.append(f"{cand_base}/index{ext}")
                    candidates.append(f"{cand_base}/mod.rs")
                    candidates.append(f"{cand_base}/__init__.py")
            except Exception:
                pass
        else:
            # Python style relative imports e.g. .models, ..utils
            dot_count = len(module_part) - len(module_part.lstrip("."))
            clean_part = module_part.lstrip(".")
            clean_slash = clean_part.replace(".", "/")
            try:
                if dot_count <= len(current_path.parents):
                    target_dir = current_path.parents[dot_count - 1]
                    cand_base = (
                        (target_dir / clean_slash).as_posix()
                        if clean_slash
                        else target_dir.as_posix()
                    )
                    candidates.append(cand_base)
                    for ext in exts:
                        candidates.append(f"{cand_base}{ext}")
                    candidates.append(f"{cand_base}/__init__.py")
            except Exception:
                pass

    # Rust module references
    elif module_part.startswith("crate::"):
        clean = module_part.removeprefix("crate::").replace("::", "/")
        candidates.extend(
            [f"src/{clean}.rs", f"src/{clean}/mod.rs", f"{clean}.rs", f"{clean}/mod.rs"]
        )
    elif module_part.startswith("super::"):
        clean = module_part.removeprefix("super::").replace("::", "/")
        try:
            target_dir = current_path.parent.parent
            cand_base = (target_dir / clean).as_posix()
            candidates.extend([f"{cand_base}.rs", f"{cand_base}/mod.rs"])
        except Exception:
            pass
    elif module_part.startswith("self::"):
        clean = module_part.removeprefix("self::").replace("::", "/")
        cand_base = (current_path.parent / clean).as_posix()
        candidates.extend([f"{cand_base}.rs", f"{cand_base}/mod.rs"])

    # C/C++ header or relative file include
    elif any(
        module_part.endswith(h_ext) for h_ext in (".h", ".hpp", ".hh", ".hxx", ".c", ".cpp", ".cc")
    ):
        candidates.append((current_path.parent / module_part).as_posix())
        candidates.append(module_part)
        candidates.append(f"src/{module_part}")
        candidates.append(f"include/{module_part}")

    # General module path (Go, Java, Python, C#, etc.)
    else:
        candidates.append((current_path.parent / module_part).as_posix())
        for ext in exts:
            candidates.append((current_path.parent / f"{module_part}{ext}").as_posix())

        clean_slash = module_part.replace(".", "/").replace("::", "/")
        candidates.append(clean_slash)
        for ext in exts:
            candidates.append(f"{clean_slash}{ext}")
            candidates.append(f"src/{clean_slash}{ext}")

        last_segment = clean_slash.split("/")[-1]
        if last_segment != clean_slash:
            candidates.extend(
                [
                    f"{last_segment}.go",
                    f"pkg/{last_segment}.go",
                    f"pkg/{last_segment}/{last_segment}.go",
                    f"src/{last_segment}.go",
                    f"src/pkg/{last_segment}/{last_segment}.go",
                ]
            )

    return candidates


class SynapRuntime:
    """Deterministic runtime service for indexing and retrieval."""

    def __init__(self, settings: SynapSettings) -> None:
        self.settings = settings
        if settings.sqlite_path is None:
            raise ValueError("Storage paths must be configured.")

        self.trace_store = TraceStore(settings.repository_path)
        self.store = SynapStore(settings.sqlite_path)
        self.git = GitRepository(settings.repository_path)
        self.parser_registry = CodeParserRegistry()
        self.llm_provider = get_llm_provider(settings)
        self.embed_provider = get_embed_provider(settings)
        self.retrieval_engine = HybridRetrievalEngine(
            repo_path=self.settings.repository_path,
            store=self.store,
            llm_provider=self.llm_provider,
            trace_store=self.trace_store,
        )
        self.logger = get_logger("runtime")

        self.wiki = WikiEngine(settings, self.store)
        self.commit_count = 0

    def shutdown(self) -> None:
        """Gracefully shutdown background tasks and executors."""

        for d in ["objects", "logs"]:
            path = self.settings.state_path / d
            if path.exists() and path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass

    def initialize_storage(self, *, auto_recover: bool = True) -> None:
        self.settings.ensure_directories()
        if auto_recover and self.store.path.exists() and self.store.recover_if_corrupted():
            self.logger.warning("database_corrupted_wiped")
        self.store.initialize()

    def _auto_protect_synap(self) -> None:
        gitignore_path = self.settings.repository_path / ".gitignore"
        patterns = [".synap/", ".synapse/", ".synapse/*-wal", ".synapse/*-shm"]
        try:
            if not gitignore_path.exists():
                gitignore_path.write_text("\n".join(patterns) + "\n", encoding="utf-8")
                return

            content = gitignore_path.read_text(encoding="utf-8")
            lines = [line.strip() for line in content.splitlines()]

            new_content = content
            added = False
            for p in patterns:
                if p.strip() not in lines and p.strip().rstrip("/") not in lines:
                    if not new_content.endswith("\n"):
                        new_content += "\n"
                    new_content += p + "\n"
                    added = True

            if added:
                gitignore_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            self.logger.warning("failed_to_auto_protect_synap", error=str(e))

    def bootstrap(self, *, force: bool = False) -> str | None:
        self.initialize_storage()
        self._auto_protect_synap()
        git_state = self.git.state(force=True)
        branch = git_state.effective_branch

        dirs = GitRepository.resolve_git_dir(self.git.path)
        git_dir = dirs[0] if dirs else self.git.path / ".git"
        merge_conflict = (
            git_state.merge_in_progress
            or (git_dir / "MERGE_HEAD").exists()
            or (git_dir / "CHERRY_PICK_HEAD").exists()
            or (git_dir / "REVERT_HEAD").exists()
        )
        rebase_in_progress = (
            git_state.rebase_in_progress
            or (git_dir / "rebase-merge").exists()
            or (git_dir / "rebase-apply").exists()
        )
        bisect_in_progress = (
            git_state.bisect_in_progress
            or (git_dir / "BISECT_LOG").exists()
            or (git_dir / "BISECT_START").exists()
        )

        if merge_conflict or rebase_in_progress or bisect_in_progress:
            self.logger.warning(
                "indexing_suspended_in_progress_operation",
                merge=merge_conflict,
                rebase=rebase_in_progress,
                bisect=bisect_in_progress,
            )
            return git_state.head_commit

        last_indexed = self.store.get_last_indexed_commit()

        if last_indexed == git_state.head_commit and not force:
            self.logger.info("bootstrap_skipped", branch=branch, commit=last_indexed)
            return last_indexed

        if last_indexed and last_indexed != git_state.head_commit and last_indexed != "unknown":
            try:
                prev = GitState(
                    repository_path=self.settings.repository_path,
                    is_repository=True,
                    head_commit=last_indexed,
                    branch=branch,
                )
                change = self.git.classify(prev, git_state)
                if change.kind == "revert":
                    self.handle_revert(prev, git_state)
                    return git_state.head_commit
            except Exception as e:
                structlog.get_logger().error("suppressed_error_caught", error=str(e))

        return self.index_repository(git_state=git_state, force=force)

    def wipe_index(self) -> None:
        """Completely purge the index to allow a fresh deterministic rebuild."""
        self.initialize_storage()
        self.store.clear_all()
        self.logger.info("index_wiped")

    def handle_commit(self, git_state: GitState) -> None:
        self.index_repository(git_state=git_state)

    def handle_branch_switch(self, git_state: GitState) -> None:
        self.initialize_storage()
        self.bootstrap()

    def handle_merge(self, git_state: GitState) -> None:
        self.index_repository(git_state=git_state)

    def handle_revert(self, previous_state: GitState | None, current_state: GitState) -> None:
        self.initialize_storage()
        revert_commit = current_state.head_commit or "unknown"
        reverted_from = previous_state.head_commit if previous_state else "unknown"

        try:
            diff_out = subprocess.check_output(  # noqa: S603
                ["git", "show", "--name-only", "--format=", revert_commit],  # noqa: S607
                cwd=self.settings.repository_path,
                text=True,
            )
            affected = [f.strip() for f in diff_out.splitlines() if f.strip()]
        except Exception:
            affected = []

        revert_msg = current_state.commit_message or ""
        prev_ref = reverted_from[:8] if reverted_from else "unknown"
        what_failed = revert_msg.splitlines()[0] if revert_msg else f"Revert of commit {prev_ref}"

        try:
            stat_out = subprocess.check_output(  # noqa: S603
                ["git", "diff", "--stat", f"{revert_commit}^!"],  # noqa: S607
                cwd=self.settings.repository_path,
                text=True,
            ).strip()
            summary = stat_out if stat_out else "Clean revert"
        except Exception:
            summary = f"Reverted changes affecting {len(affected)} files"

        why_failed = f"Automated revert analysis: {summary}"

        now = int(datetime.now(UTC).timestamp())

        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT INTO lessons (lesson_id, branch, revert_commit, reverted_from, what_failed, why_failed, files_affected, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    current_state.effective_branch,
                    revert_commit,
                    reverted_from,
                    what_failed,
                    why_failed,
                    json.dumps(affected),
                    now,
                    now + (86400 * self.settings.lesson_expiry_days),
                ),
            )

        self.logger.info("lesson_pending", revert_commit=revert_commit, reverted_from=reverted_from)
        self.index_repository(git_state=current_state)

    def index_repository(
        self, *, git_state: GitState | None = None, force: bool = False
    ) -> str | None:
        git_state = git_state or self.git.state(force=True)
        branch = git_state.effective_branch

        dirs = GitRepository.resolve_git_dir(self.git.path)
        git_dir = dirs[0] if dirs else self.git.path / ".git"
        merge_conflict = (
            git_state.merge_in_progress
            or (git_dir / "MERGE_HEAD").exists()
            or (git_dir / "CHERRY_PICK_HEAD").exists()
            or (git_dir / "REVERT_HEAD").exists()
        )
        rebase_in_progress = (
            git_state.rebase_in_progress
            or (git_dir / "rebase-merge").exists()
            or (git_dir / "rebase-apply").exists()
        )
        bisect_in_progress = (
            git_state.bisect_in_progress
            or (git_dir / "BISECT_LOG").exists()
            or (git_dir / "BISECT_START").exists()
        )

        if merge_conflict or rebase_in_progress or bisect_in_progress:
            self.logger.warning(
                "indexing_suspended_in_progress_operation",
                merge=merge_conflict,
                rebase=rebase_in_progress,
                bisect=bisect_in_progress,
            )
            return git_state.head_commit

        # Determine last commit indexed in SQLite
        last_indexed: str | None = None
        if self.store.path.exists():
            last_indexed = self.store.get_last_indexed_commit()
            if last_indexed == git_state.head_commit and not force:
                self.logger.info(
                    "index_repository_skipped",
                    branch=branch,
                    commit=last_indexed,
                )
                return last_indexed

        self.initialize_storage()

        # Check active commit after storage initialization
        if last_indexed is None:
            last_indexed = self.store.get_last_indexed_commit()

        # Determine if we should run first-run or incremental
        if (
            last_indexed is None
            or force
            or last_indexed == "unknown"
            or not git_state.is_repository
        ):
            commit = self._first_run_index(git_state)
        else:
            commit = self._incremental_index(last_indexed, git_state)

        # Automatic periodic checkpointing (unrelated to indexing itself, but keeps spec compatibility)
        self.commit_count += 1
        if self.commit_count % 10 == 0:
            self.store.put_checkpoint(
                checkpoint_id=str(uuid.uuid4()),
                branch=git_state.effective_branch,
                commit_hash=git_state.head_commit or "unknown",
                doing="Automatic periodic checkpoint",
                changed_files="[]",
                next_step="",
                blockers="",
            )
            self.logger.info("auto_checkpoint_created", commit=git_state.head_commit)

        return commit

    def _generate_embeddings(
        self, symbols_to_embed: list[tuple[str, list[dict[str, Any]], str]]
    ) -> None:
        provider = self.embed_provider
        if not provider or not symbols_to_embed:
            return

        total_symbols = sum(len(syms) for _, syms, _ in symbols_to_embed)
        if total_symbols == 0:
            return

        model_name = getattr(provider, "default_model", "unknown")

        for file_id, symbols, content_hash in symbols_to_embed:
            for sym in symbols:
                try:
                    text = sym["name"] + " " + (sym.get("metadata") or {}).get("docstring", "")
                    vector = provider.embed(text)
                    if vector:
                        self.store.put_embedding(
                            sym["symbol_id"], model_name, "1.0", "1.0", vector, content_hash
                        )
                except KeyboardInterrupt:
                    self.logger.warning("embedding_interrupted_by_user")
                    raise
                except NotImplementedError:
                    self.logger.warning(
                        "embedding_not_supported", provider=provider.__class__.__name__
                    )
                    return
                except Exception as e:
                    self.logger.debug(
                        "embedding_failed_for_symbol", symbol=sym["name"], error=str(e)
                    )

    def _first_run_index(self, git_state: GitState) -> str | None:
        self.logger.info("first_run_indexing_started", branch=git_state.effective_branch)

        t_start = time.perf_counter()

        scanner = RepositoryScanner(
            repository_path=self.settings.repository_path,
            max_file_bytes=self.settings.max_file_bytes,
        )
        num_files = scanner.count_files()
        chunk_size = 500
        parsed_results = []
        symbols_to_embed = []
        scanned_paths: set[str] = set()
        # Parallel parsing using ProcessPoolExecutor

        num_workers = max(1, multiprocessing.cpu_count())
        self.logger.info("parallel_parsing_started", files=num_files, workers=num_workers)

        console = Console(stderr=True)
        show_progress = self.settings.logging_mode.name == "HUMAN" and num_files > 5

        if show_progress:
            console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
            console.print(
                f"[bold cyan]  Building Structural Index: [white]{git_state.effective_branch}[/white][/bold cyan]"
            )
            console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")

        # Enqueue special project wikis
        self.store.enqueue_wiki("overview.md")
        self.store.enqueue_wiki("architecture.md")
        self.store.enqueue_wiki("schema.md")

        if show_progress:
            with Progress(
                SpinnerColumn("line"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("[yellow]Parsing codebase...[/yellow]", total=num_files)

                with ProcessPoolExecutor(max_workers=num_workers) as executor:
                    file_iterator = scanner.scan()
                    while True:
                        chunk_files = list(islice(file_iterator, chunk_size))
                        if not chunk_files:
                            break

                        file_info_map = {f.relative_path: f for f in chunk_files}
                        chunk = [(f.path, f.relative_path) for f in chunk_files]
                        futures = [executor.submit(_parse_worker, item) for item in chunk]
                        chunk_results = [f.result() for f in futures]

                        for res in chunk_results:
                            rel_path = res["path"]
                            scanned_paths.add(rel_path)
                            matching_info = file_info_map.get(rel_path)
                            git_oid = matching_info.git_oid if matching_info else ""
                            content_hash = matching_info.content_hash if matching_info else ""

                            file_id_hash = hashlib.sha256(
                                (rel_path + content_hash).encode("utf-8")
                            ).hexdigest()

                            self.store.upsert_file_and_symbols(
                                file_id=file_id_hash,
                                path=rel_path,
                                git_oid=git_oid or "",
                                content_hash=content_hash,
                                language=res["language"],
                                symbols=res["symbols"],
                            )
                            symbols_to_embed.append((file_id_hash, res["symbols"], content_hash))
                            if self.settings.enable_file_wiki:
                                self.store.enqueue_wiki(rel_path)
                            parsed_results.append((file_id_hash, rel_path, res["imports"]))

                        # Generate Embeddings Synchronously
                        self._generate_embeddings(symbols_to_embed)
                        symbols_to_embed.clear()

                        # Resolve edges for this chunk to keep memory bounded (MEDIUM-002)
                        if parsed_results:
                            self._resolve_and_insert_edges(parsed_results)
                            parsed_results.clear()

                        progress.advance(task, len(chunk_files))
                        del chunk_results
        else:
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                file_iterator = scanner.scan()
                while True:
                    chunk_files = list(islice(file_iterator, chunk_size))
                    if not chunk_files:
                        break

                    file_info_map = {f.relative_path: f for f in chunk_files}
                    chunk = [(f.path, f.relative_path) for f in chunk_files]
                    futures = [executor.submit(_parse_worker, item) for item in chunk]
                    chunk_results = [f.result() for f in futures]

                    for res in chunk_results:
                        rel_path = res["path"]
                        scanned_paths.add(rel_path)
                        matching_info = file_info_map.get(rel_path)
                        git_oid = matching_info.git_oid if matching_info else ""
                        content_hash = matching_info.content_hash if matching_info else ""

                        file_id_hash = hashlib.sha256(
                            (rel_path + content_hash).encode("utf-8")
                        ).hexdigest()

                        self.store.upsert_file_and_symbols(
                            file_id=file_id_hash,
                            path=rel_path,
                            git_oid=git_oid or "",
                            content_hash=content_hash,
                            language=res["language"],
                            symbols=res["symbols"],
                        )
                        symbols_to_embed.append((file_id_hash, res["symbols"], content_hash))
                        if self.settings.enable_file_wiki:
                            self.store.enqueue_wiki(rel_path)
                        parsed_results.append((file_id_hash, rel_path, res["imports"]))

                    # Generate Embeddings Synchronously
                    self._generate_embeddings(symbols_to_embed)
                    symbols_to_embed.clear()

                    # Resolve edges for this chunk to keep memory bounded (MEDIUM-002)
                    if parsed_results:
                        self._resolve_and_insert_edges(parsed_results)
                        parsed_results.clear()

                    del chunk_results

        # Pass 2: Final edge resolution
        if parsed_results:
            self.logger.info("structural_edge_resolution_started")
            self._resolve_and_insert_edges(parsed_results)

        # Clean up stale ghost files that no longer exist in the working tree
        with self.store.connect() as conn:
            existing_rows = conn.execute("SELECT file_id, path FROM files").fetchall()
            stale_file_ids = [
                row["file_id"] for row in existing_rows if row["path"] not in scanned_paths
            ]
            for fid in stale_file_ids:
                conn.execute(
                    "DELETE FROM edges WHERE source_symbol IN (SELECT symbol_id FROM symbols WHERE file_id = ?) OR target_symbol IN (SELECT symbol_id FROM symbols WHERE file_id = ?)",
                    (fid, fid),
                )
                conn.execute("DELETE FROM symbols WHERE file_id = ?", (fid,))
                conn.execute("DELETE FROM files WHERE file_id = ?", (fid,))
            conn.execute(
                "DELETE FROM edges WHERE source_symbol NOT IN (SELECT symbol_id FROM symbols) OR target_symbol NOT IN (SELECT symbol_id FROM symbols)"
            )
            conn.execute("DELETE FROM symbols WHERE file_id NOT IN (SELECT file_id FROM files)")

        # Set active commit
        self.store.set_active_commit(git_state.effective_branch, git_state.head_commit or "unknown")

        self.logger.info("first_run_indexing_completed", elapsed_sec=time.perf_counter() - t_start)
        return git_state.head_commit

    def _incremental_index(self, previous_commit: str, git_state: GitState) -> str | None:
        self.logger.info(
            "incremental_indexing_started",
            previous_commit=previous_commit,
            current_commit=git_state.head_commit,
        )

        t_start = time.perf_counter()

        if not git_state.is_repository or not git_state.head_commit or previous_commit == "unknown":
            self.logger.warning("fallback_to_first_run_no_git_commit")
            return self._first_run_index(git_state)

        try:
            res = subprocess.run(
                [
                    "git",
                    "diff-tree",
                    "-r",
                    "-M",
                    "--no-commit-id",
                    "--name-status",
                    previous_commit,
                    git_state.head_commit,
                ],
                cwd=self.settings.repository_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception as e:
            self.logger.error("git_diff_tree_failed", error=str(e))
            return self._first_run_index(git_state)

        added_or_modified = []
        deleted = []
        renames = []
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                status = parts[0]
                if status.startswith("R"):
                    renames.append((parts[1], parts[2]))
                    added_or_modified.append(parts[2])
                elif status == "D":
                    deleted.append(parts[1])
                else:
                    added_or_modified.append(parts[1])

        # Apply renames to preserve identity
        with self.store.connect() as conn:
            for old_path, new_path in renames:
                file_row = conn.execute(
                    "SELECT file_id, content_hash FROM files WHERE path = ?", (old_path,)
                ).fetchone()
                if file_row:
                    old_file_id = file_row["file_id"]
                    content_hash = file_row["content_hash"]
                    new_file_id = hashlib.sha256(
                        (new_path + content_hash).encode("utf-8")
                    ).hexdigest()

                    conn.execute("PRAGMA foreign_keys=OFF")
                    try:
                        conn.execute(
                            "UPDATE files SET file_id = ?, path = ? WHERE file_id = ?",
                            (new_file_id, new_path, old_file_id),
                        )
                        conn.execute(
                            "UPDATE symbols SET file_id = ? WHERE file_id = ?",
                            (new_file_id, old_file_id),
                        )
                    finally:
                        conn.execute("PRAGMA foreign_keys=ON")

        # Filter added/modified files
        scanner = RepositoryScanner(
            repository_path=self.settings.repository_path,
            max_file_bytes=self.settings.max_file_bytes,
        )

        filtered_added_or_modified = []
        for rel_path in added_or_modified:
            p = self.settings.repository_path / rel_path
            if not p.exists() or not p.is_file():
                continue
            if scanner._excluded(p):
                continue
            try:
                if p.stat().st_size > self.settings.max_file_bytes:
                    continue
            except OSError:
                continue

            if _is_binary_file(p):
                continue
            filtered_added_or_modified.append(rel_path)

        self.logger.info(
            "git_delta_parsed",
            added_or_modified=len(filtered_added_or_modified),
            deleted=len(deleted),
        )

        if not filtered_added_or_modified and not deleted:
            self.store.set_active_commit(
                git_state.effective_branch, git_state.head_commit or "unknown"
            )
            self.logger.info(
                "incremental_indexing_completed", elapsed_sec=time.perf_counter() - t_start
            )
            return git_state.head_commit

        # Handle deletions
        with self.store.connect() as conn:
            for rel_path in deleted:
                self.logger.info("deleting_file_index", path=rel_path)
                file_row = conn.execute(
                    "SELECT file_id FROM files WHERE path = ?", (rel_path,)
                ).fetchone()
                if file_row:
                    file_id = file_row["file_id"]
                    conn.execute(
                        "DELETE FROM edges WHERE source_symbol IN (SELECT symbol_id FROM symbols WHERE file_id = ?) OR target_symbol IN (SELECT symbol_id FROM symbols WHERE file_id = ?)",
                        (file_id, file_id),
                    )
                    conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
                    conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
                else:
                    conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))

            # Clean up ghost files deleted or untracked in Git
            try:
                tracked_res = subprocess.run(
                    ["git", "ls-files", "-z", "-c", "--exclude-standard"],
                    cwd=self.settings.repository_path,
                    capture_output=True,
                    check=True,
                )
                tracked_set = {
                    p.decode("utf-8", errors="replace")
                    for p in tracked_res.stdout.split(b"\0")
                    if p
                }
                existing_rows = conn.execute("SELECT file_id, path FROM files").fetchall()
                for row in existing_rows:
                    if row["path"] not in tracked_set:
                        fid = row["file_id"]
                        conn.execute(
                            "DELETE FROM edges WHERE source_symbol IN (SELECT symbol_id FROM symbols WHERE file_id = ?) OR target_symbol IN (SELECT symbol_id FROM symbols WHERE file_id = ?)",
                            (fid, fid),
                        )
                        conn.execute("DELETE FROM symbols WHERE file_id = ?", (fid,))
                        conn.execute("DELETE FROM files WHERE file_id = ?", (fid,))
            except Exception as e:
                self.logger.debug("ghost_file_check_skipped", error=str(e))

            # Purge any dangling edges or symbols
            conn.execute(
                "DELETE FROM edges WHERE source_symbol NOT IN (SELECT symbol_id FROM symbols) OR target_symbol NOT IN (SELECT symbol_id FROM symbols)"
            )
            conn.execute("DELETE FROM symbols WHERE file_id NOT IN (SELECT file_id FROM files)")

        for rel_path in deleted:
            self.store.set_wiki_status(rel_path, None, "stale")

        # Get blob OIDs for changed files
        git_oids = {}
        if filtered_added_or_modified:
            try:
                cmd = ["git", "ls-tree", "HEAD"] + filtered_added_or_modified
                res_tree = subprocess.run(
                    cmd,
                    cwd=self.settings.repository_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                for line in res_tree.stdout.splitlines():
                    if not line.strip():
                        continue
                    line_parts = line.split("\t", 1)
                    if len(line_parts) == 2:
                        meta = line_parts[0].split()
                        if len(meta) >= 3:
                            oid = meta[2]
                            path = line_parts[1]
                            git_oids[path] = oid
            except Exception as e:
                self.logger.warning("git_ls_tree_failed", error=str(e))

        # Process additions and modifications
        registry = CodeParserRegistry()
        parsed_results = []
        symbols_to_embed = []

        console = Console(stderr=True)
        show_progress = (
            self.settings.logging_mode.name == "HUMAN" and len(filtered_added_or_modified) > 0
        )

        with (
            console.status(
                "[yellow]Parsing incrementally changed files...[/yellow]", spinner="line"
            )
            if show_progress
            else contextlib.nullcontext()
        ) as status_ctx:
            for idx, rel_path in enumerate(filtered_added_or_modified, 1):
                if show_progress and hasattr(status_ctx, "update"):
                    status_ctx.update(  # type: ignore[union-attr]
                        f"[yellow]Parsing incrementally changed files ([white]{idx}/{len(filtered_added_or_modified)}[/white])...[/yellow]"
                    )

                self.logger.info("reindexing_file", path=rel_path)
                p = self.settings.repository_path / rel_path

                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    self.logger.warning("failed_to_read_file", path=rel_path, error=str(e))
                    continue

                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                file_id_hash = hashlib.sha256((rel_path + content_hash).encode("utf-8")).hexdigest()

                parse_result = registry.parse(p, relative_path=rel_path, text=content)
                symbols_list = [
                    {
                        "symbol_id": sym.stable_id,
                        "name": sym.name,
                        "kind": sym.kind,
                        "start_line": sym.start_line,
                        "end_line": sym.end_line,
                        "ast_hash": sym.ast_hash,
                        "metadata": sym.metadata,
                    }
                    for sym in parse_result.symbols
                ]

                self.store.upsert_file_and_symbols(
                    file_id=file_id_hash,
                    path=rel_path,
                    git_oid=git_oids.get(rel_path, ""),
                    content_hash=content_hash,
                    language=parse_result.language,
                    symbols=symbols_list,
                )
                symbols_to_embed.append((file_id_hash, symbols_list, content_hash))

                if self.settings.enable_file_wiki:
                    self.store.set_wiki_status(rel_path, None, "stale")
                    self.store.enqueue_wiki(rel_path)

                with self.store.connect() as conn:
                    conn.execute(
                        "DELETE FROM edges WHERE source_symbol IN (SELECT symbol_id FROM symbols WHERE file_id = ?)",
                        (file_id_hash,),
                    )

                parsed_results.append((file_id_hash, rel_path, list(parse_result.imports)))

        # Generate Embeddings Synchronously
        self._generate_embeddings(symbols_to_embed)

        # Re-resolve edges for changed files
        if parsed_results:
            self.logger.info("re_resolving_edges")
            self._resolve_and_insert_edges(parsed_results)

        # Set active commit
        self.store.set_active_commit(git_state.effective_branch, git_state.head_commit or "unknown")

        self.logger.info(
            "incremental_indexing_completed", elapsed_sec=time.perf_counter() - t_start
        )
        return git_state.head_commit

    def _resolve_and_insert_edges(self, parsed_results: list[tuple[str, str, list[str]]]) -> None:
        if not parsed_results:
            return

        with self.store.connect() as conn:
            all_files = conn.execute("SELECT file_id, path, module_key FROM files").fetchall()
            if not all_files:
                return

            path_to_file_id: dict[str, str] = {row["path"]: row["file_id"] for row in all_files}
            module_key_to_file_id: dict[str, str] = {
                row["module_key"]: row["file_id"] for row in all_files if row["module_key"]
            }
            filename_to_file_ids: dict[str, list[str]] = {}
            for row in all_files:
                fname = Path(row["path"]).name
                filename_to_file_ids.setdefault(fname, []).append(row["file_id"])

            source_file_ids = {r[0] for r in parsed_results}
            file_symbols_map: dict[str, list[dict[str, Any]]] = {}
            sf_list = list(source_file_ids)
            for i in range(0, len(sf_list), 900):
                chunk = sf_list[i : i + 900]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT file_id, symbol_id, name, metadata_json FROM symbols WHERE file_id IN ({placeholders})",  # noqa: S608  # nosec B608
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    meta = {}
                    if row["metadata_json"]:
                        try:
                            meta = json.loads(row["metadata_json"])
                        except Exception:
                            pass
                    file_symbols_map.setdefault(row["file_id"], []).append(
                        {
                            "file_id": row["file_id"],
                            "symbol_id": row["symbol_id"],
                            "name": row["name"],
                            "refs": set(meta.get("refs", [])),
                        }
                    )

            def find_target_file_id(current_rel_path: str, module_part: str) -> str | None:
                cand_paths = _generate_candidate_paths(current_rel_path, module_part)
                for cand in cand_paths:
                    if cand in path_to_file_id:
                        return path_to_file_id[cand]

                if module_part in module_key_to_file_id:
                    return module_key_to_file_id[module_part]

                fname = Path(module_part).name
                if fname in filename_to_file_ids:
                    return filename_to_file_ids[fname][0]

                clean_mod = module_part.removeprefix("crate::").replace("::", ".").replace("/", ".")
                if clean_mod in module_key_to_file_id:
                    return module_key_to_file_id[clean_mod]

                last_part = clean_mod.split(".")[-1]
                if last_part in module_key_to_file_id:
                    return module_key_to_file_id[last_part]

                for mk, fid in module_key_to_file_id.items():
                    if (
                        mk == clean_mod
                        or mk.endswith(f".{clean_mod}")
                        or clean_mod.endswith(f".{mk}")
                        or clean_mod.endswith(f".{last_part}")
                        or mk.endswith(f".{last_part}")
                    ):
                        return fid

                return None

            target_file_ids: set[str] = set()
            resolved_imports_by_file: list[tuple[str, str, list[tuple[str, str | None, str]]]] = []

            for file_id, rel_path, imports in parsed_results:
                file_resolved: list[tuple[str, str | None, str]] = []
                for imp in imports:
                    if _is_stdlib_module(imp):
                        continue

                    if ":" in imp:
                        module_part, target_name = imp.split(":", 1)
                    else:
                        module_part, target_name = imp, None

                    t_file_id = find_target_file_id(rel_path, module_part)
                    if t_file_id and t_file_id != file_id:
                        target_file_ids.add(t_file_id)
                        file_resolved.append((t_file_id, target_name, module_part))

                resolved_imports_by_file.append((file_id, rel_path, file_resolved))

            target_symbols_dict: dict[str, dict[str, list[dict[str, Any]]]] = {}
            if target_file_ids:
                tf_list = list(target_file_ids)
                for i in range(0, len(tf_list), 900):
                    chunk = tf_list[i : i + 900]
                    placeholders = ",".join("?" for _ in chunk)
                    rows = conn.execute(
                        f"SELECT file_id, symbol_id, name FROM symbols WHERE file_id IN ({placeholders})",  # noqa: S608  # nosec B608
                        tuple(chunk),
                    ).fetchall()
                    for row in rows:
                        target_symbols_dict.setdefault(row["file_id"], {}).setdefault(
                            row["name"], []
                        ).append(dict(row))

            edges_to_insert = []
            for file_id, rel_path, resolved_imports in resolved_imports_by_file:
                file_symbols = file_symbols_map.get(file_id, [])
                edges_added_for_file = 0
                max_edges_per_file = 1000

                for t_file_id, target_name, module_part in resolved_imports:
                    if edges_added_for_file >= max_edges_per_file:
                        break

                    sym_map = target_symbols_dict.get(t_file_id, {})
                    if not sym_map:
                        continue

                    if target_name and target_name in sym_map:
                        target_symbols = sym_map[target_name]
                    else:
                        target_symbols = [s for sym_list in sym_map.values() for s in sym_list]

                    mod_alias = module_part.split("/")[-1].split("::")[-1].split(".")[-1]

                    for ts in target_symbols:
                        if edges_added_for_file >= max_edges_per_file:
                            break

                        for fs in file_symbols:
                            if edges_added_for_file >= max_edges_per_file:
                                break
                            if fs["symbol_id"] == ts["symbol_id"]:
                                continue

                            fs_refs = fs.get("refs")
                            if fs_refs:
                                if ts["name"] not in fs_refs and mod_alias not in fs_refs:
                                    continue
                            elif target_name and target_name != ts["name"]:
                                continue

                            edge_id = stable_hash(
                                {
                                    "source": fs["symbol_id"],
                                    "target": ts["symbol_id"],
                                    "type": "depends_on",
                                }
                            )
                            edges_to_insert.append((edge_id, fs["symbol_id"], ts["symbol_id"]))
                            edges_added_for_file += 1

            if edges_to_insert:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO edges (edge_id, source_symbol, target_symbol, edge_type)
                    VALUES (?, ?, ?, 'depends_on')
                    """,
                    edges_to_insert,
                )

    def status(self) -> RuntimeStatus:
        self.initialize_storage()
        git_state = self.git.state()
        active_commit = self.store.get_active_commit(git_state.effective_branch)

        with self.store.connect() as conn:
            symbol_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

        return RuntimeStatus(
            repository_path=self.settings.repository_path.as_posix(),
            branch=git_state.effective_branch,
            git_commit=git_state.head_commit,
            active_commit=active_commit,
            symbols=symbol_count,
            files=file_count,
            mode=self.settings.mode.value,
            is_dirty=git_state.is_dirty,
        )

    def query_hybrid(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        synthesize_answer: bool = True,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        self.initialize_storage()
        is_dirty = False
        try:
            is_dirty = self.git.state().is_dirty
        except Exception as e:
            structlog.get_logger().error("suppressed_error_caught", error=str(e))
        return self.retrieval_engine.retrieve(
            query,
            max_tokens=max_tokens,
            is_dirty=is_dirty,
            synthesize_answer=synthesize_answer,
        )

    def doctor(self, *, auto_recover: bool = False) -> dict[str, Any]:
        self.initialize_storage(auto_recover=auto_recover)
        with self.store.connect() as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "database_integrity": integrity,
            "status": self.status().__dict__,
        }
