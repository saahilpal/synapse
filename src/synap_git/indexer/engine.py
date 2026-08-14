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
        existing_commit = self.store.get_active_commit(branch)

        if existing_commit == git_state.head_commit and not force:
            self.logger.info("bootstrap_skipped", branch=branch, commit=existing_commit)
            return existing_commit

        if (
            existing_commit
            and existing_commit != git_state.head_commit
            and existing_commit != "unknown"
        ):
            try:
                prev = GitState(
                    repository_path=self.settings.repository_path,
                    is_repository=True,
                    head_commit=existing_commit,
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
                    "Revert detected automatically",
                    "Awaiting analysis from LLM or User",
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

        # If the current repository commit is already indexed, skip reindexing entirely.
        if self.store.path.exists():
            existing_commit = self.store.get_active_commit(branch)
            if existing_commit == git_state.head_commit and not force:
                self.logger.info(
                    "index_repository_skipped",
                    branch=branch,
                    commit=existing_commit,
                )
                return existing_commit
        else:
            existing_commit = None

        self.initialize_storage()

        # Check active commit after storage initialization
        if existing_commit is None:
            existing_commit = self.store.get_active_commit(branch)

        # Determine if we should run first-run or incremental
        if (
            existing_commit is None
            or force
            or existing_commit == "unknown"
            or not git_state.is_repository
        ):
            commit = self._first_run_index(git_state)
        else:
            commit = self._incremental_index(existing_commit, git_state)

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
                    conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))

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
        edges_to_insert = []
        source_file_ids = set()
        candidate_paths = set()
        module_keys = set()
        fts_names = set()

        for file_id, rel_path, imports in parsed_results:
            source_file_ids.add(file_id)
            current_path = Path(rel_path)
            for imp in imports:
                if ":" in imp:
                    module_part, target_name = imp.split(":", 1)
                else:
                    module_part, target_name = imp, imp.split(".")[-1]

                if module_part.startswith("."):
                    parts = module_part.lstrip(".").split(".")
                    dot_count = len(module_part) - len(module_part.lstrip("."))
                    try:
                        target_dir = current_path.parents[dot_count - 1]
                        candidate_rel = (target_dir / "/".join(parts)).as_posix()
                        for ext in [
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
                        ]:
                            candidate_paths.add(f"{candidate_rel}{ext}")
                    except Exception as e:
                        structlog.get_logger().error("suppressed_error_caught", error=str(e))
                else:
                    module_keys.add(module_part)
                fts_names.add(target_name)

        with self.store.connect() as conn:
            file_symbols_map: dict[str, list[dict[str, Any]]] = {}
            if source_file_ids:
                sf_list = list(source_file_ids)
                for i in range(0, len(sf_list), 900):
                    chunk = sf_list[i : i + 900]
                    placeholders = ",".join("?" for _ in chunk)
                    rows = conn.execute(
                        f"SELECT file_id, symbol_id, name FROM symbols WHERE file_id IN ({placeholders})",  # noqa: S608  # nosec B608
                        tuple(chunk),
                    ).fetchall()
                    for row in rows:
                        file_symbols_map.setdefault(row["file_id"], []).append(dict(row))

            path_to_file_id = {}
            if candidate_paths:
                paths_list = list(candidate_paths)
                for i in range(0, len(paths_list), 900):
                    chunk = paths_list[i : i + 900]
                    placeholders = ",".join("?" for _ in chunk)
                    rows = conn.execute(
                        f"SELECT file_id, path FROM files WHERE path IN ({placeholders})",  # noqa: S608  # nosec B608
                        tuple(chunk),
                    ).fetchall()
                    for row in rows:
                        path_to_file_id[row["path"]] = row["file_id"]

            module_key_to_file_id = {}
            if module_keys:
                mk_list = list(module_keys)
                for i in range(0, len(mk_list), 900):
                    chunk = mk_list[i : i + 900]
                    placeholders = ",".join("?" for _ in chunk)
                    rows = conn.execute(
                        f"SELECT file_id, module_key FROM files WHERE module_key IN ({placeholders})",  # noqa: S608  # nosec B608
                        tuple(chunk),
                    ).fetchall()
                    for row in rows:
                        module_key_to_file_id[row["module_key"]] = row["file_id"]

            target_file_ids = set()
            for file_id, rel_path, imports in parsed_results:
                current_path = Path(rel_path)
                for imp in imports:
                    if ":" in imp:
                        module_part, target_name = imp.split(":", 1)
                    else:
                        module_part, target_name = imp, imp.split(".")[-1]

                    target_file_id = None
                    if module_part.startswith("."):
                        parts = module_part.lstrip(".").split(".")
                        dot_count = len(module_part) - len(module_part.lstrip("."))
                        try:
                            target_dir = current_path.parents[dot_count - 1]
                            candidate_rel = (target_dir / "/".join(parts)).as_posix()
                            for ext in [
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
                            ]:
                                cand_path = f"{candidate_rel}{ext}"
                                if cand_path in path_to_file_id:
                                    target_file_id = path_to_file_id[cand_path]
                                    break
                        except Exception as e:
                            structlog.get_logger().error("suppressed_error_caught", error=str(e))
                    else:
                        target_file_id = module_key_to_file_id.get(module_part)

                    if target_file_id:
                        target_file_ids.add(target_file_id)

            target_symbols_by_file: dict[str, list[dict[str, Any]]] = {}
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
                        target_symbols_by_file.setdefault(row["file_id"], []).append(dict(row))

            fts_symbols_by_name: dict[str, list[dict[str, Any]]] = {}
            if fts_names:
                fts_list = list(fts_names)
                for i in range(0, len(fts_list), 900):
                    chunk = fts_list[i : i + 900]
                    placeholders = ",".join("?" for _ in chunk)
                    rows = conn.execute(  # nosec B608
                        f"SELECT symbol_id, name FROM symbols WHERE name IN ({placeholders})",  # noqa: S608  # nosec B608
                        tuple(chunk),
                    ).fetchall()
                    for row in rows:
                        fts_symbols_by_name.setdefault(row["name"], []).append(dict(row))

            target_symbols_dict: dict[str, dict[str, list[dict[str, Any]]]] = {}
            for t_file_id, syms in target_symbols_by_file.items():
                name_map: dict[str, Any] = {}
                for sym in syms:
                    name_map.setdefault(sym["name"], []).append(sym)
                target_symbols_dict[t_file_id] = name_map

            for file_id, rel_path, imports in parsed_results:
                file_symbols = file_symbols_map.get(file_id, [])
                current_path = Path(rel_path)
                edges_added_for_file = 0
                max_edges_per_file = 1000

                for imp in imports:
                    if edges_added_for_file >= max_edges_per_file:
                        break

                    target_file_id = None
                    if ":" in imp:
                        module_part, target_name = imp.split(":", 1)
                    else:
                        module_part, target_name = imp, imp.split(".")[-1]

                    if module_part.startswith("."):
                        parts = module_part.lstrip(".").split(".")
                        dot_count = len(module_part) - len(module_part.lstrip("."))
                        try:
                            target_dir = current_path.parents[dot_count - 1]
                            candidate_rel = (target_dir / "/".join(parts)).as_posix()
                            for ext in [
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
                            ]:
                                cand_path = f"{candidate_rel}{ext}"
                                if cand_path in path_to_file_id:
                                    target_file_id = path_to_file_id[cand_path]
                                    break
                        except Exception as e:
                            structlog.get_logger().error("suppressed_error_caught", error=str(e))
                    else:
                        target_file_id = module_key_to_file_id.get(module_part)

                        # Fuzzy fallback
                        if not target_file_id:
                            for mk, fid in module_key_to_file_id.items():
                                if mk.endswith(module_part) or mk.endswith(f".{module_part}"):
                                    target_file_id = fid
                                    break

                    target_symbols = []
                    if target_file_id:
                        target_symbols = target_symbols_dict.get(target_file_id, {}).get(
                            target_name, []
                        )
                    else:
                        target_symbols = fts_symbols_by_name.get(target_name, [])

                    for ts in target_symbols:
                        if edges_added_for_file >= max_edges_per_file:
                            break
                        for fs in file_symbols:
                            if edges_added_for_file >= max_edges_per_file:
                                break
                            if fs["symbol_id"] == ts["symbol_id"]:
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
