from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synap_git.config import SynapSettings
from synap_git.diagnostics.logger import get_logger
from synap_git.git import GitRepository, GitState
from synap_git.indexer.scanner import RepositoryScanner
from synap_git.parser.registry import CodeParserRegistry
from synap_git.provider.factory import get_llm_provider
from synap_git.retrieval.engine import HybridRetrievalEngine
from synap_git.storage.sqlite import SynapStore
from synap_git.utils.serialization import stable_hash


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

        from synap_git.diagnostics.tracing import TraceStore

        self.trace_store = TraceStore(settings.repository_path)
        self.store = SynapStore(settings.sqlite_path)
        self.git = GitRepository(settings.repository_path)
        self.parser_registry = CodeParserRegistry()
        self.llm_provider = get_llm_provider(settings)
        self.retrieval_engine = HybridRetrievalEngine(
            store=self.store,
            llm_provider=self.llm_provider,
            trace_store=self.trace_store,
        )
        self.logger = get_logger("runtime")

        from synap_git.indexer.wiki import WikiEngine

        self.wiki = WikiEngine(settings, self.store)
        self.commit_count = 0

    def initialize_storage(self) -> None:
        self.settings.ensure_directories()
        if self.store.path.exists() and self.store.recover_if_corrupted():
            self.logger.warning("database_corrupted_wiped")
        self.store.initialize()

    def _auto_protect_synap(self) -> None:
        gitignore_path = self.settings.repository_path / ".gitignore"
        try:
            if not gitignore_path.exists():
                gitignore_path.write_text(".synap/\n", encoding="utf-8")
                return

            content = gitignore_path.read_text(encoding="utf-8")
            lines = [line.strip() for line in content.splitlines()]
            if ".synap/" not in lines and ".synap" not in lines:
                if content and not content.endswith("\n"):
                    content += "\n"
                content += ".synap/\n"
                gitignore_path.write_text(content, encoding="utf-8")
        except Exception as e:
            self.logger.warning("failed_to_auto_protect_synap", error=str(e))

    def bootstrap(self, *, force: bool = False) -> str | None:
        self.initialize_storage()
        self._auto_protect_synap()
        git_state = self.git.state()
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
                from synap_git.git.state import GitState

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
            except Exception:
                pass

        return self.index_repository(git_state=git_state)

    def wipe_index(self) -> None:
        """Completely purge the index to allow a fresh deterministic rebuild."""
        self.initialize_storage()
        self.store.clear_all()
        self.logger.info("index_wiped")

    def handle_commit(self, git_state: GitState) -> None:
        self.index_repository(git_state=git_state)
        # Pass 2 happens inside index_repository eventually

    def handle_branch_switch(self, git_state: GitState) -> None:
        self.initialize_storage()
        self.bootstrap()

    def handle_merge(self, git_state: GitState) -> None:
        self.index_repository(git_state=git_state)

    def handle_revert(self, previous_state: GitState | None, current_state: GitState) -> None:
        self.initialize_storage()
        revert_commit = current_state.head_commit or "unknown"
        reverted_from = previous_state.head_commit if previous_state else "unknown"

        import json
        import subprocess
        import uuid
        from datetime import UTC, datetime

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
                    now + (86400 * 7),  # 7 days
                ),
            )

        self.logger.info("lesson_pending", revert_commit=revert_commit, reverted_from=reverted_from)
        self.index_repository(git_state=current_state)

    def index_repository(self, *, git_state: GitState | None = None) -> str | None:
        self.initialize_storage()
        git_state = git_state or self.git.state()
        scanner = RepositoryScanner(
            repository_path=self.settings.repository_path,
            max_file_bytes=self.settings.max_file_bytes,
        )
        scan = scanner.scan()

        all_parse_results = []

        # Pass 1: Index all symbols
        for file_info in scan.files:
            rel_path = file_info.relative_path
            existing = self.store.get_file_by_path(rel_path)

            if existing and existing["content_hash"] == file_info.content_hash:
                # Still need the parse result for Pass 2 if we want to update edges
                # For now, let's just reparse changed files
                continue

            self.logger.info("indexing_file", path=rel_path)

            import hashlib

            file_id_input = rel_path
            file_id_hash = hashlib.sha256(file_id_input.encode()).hexdigest()

            parse_result = self.parser_registry.parse(file_info.path, relative_path=rel_path)
            all_parse_results.append((file_id_hash, parse_result))

            symbols_list = []
            for sym in parse_result.symbols:
                symbols_list.append(
                    {
                        "symbol_id": sym.stable_id,
                        "name": sym.name,
                        "kind": sym.kind,
                        "start_line": sym.start_line,
                        "end_line": sym.end_line,
                        "ast_hash": sym.ast_hash,
                        "metadata": sym.metadata,
                    }
                )

            file_id = self.store.upsert_file_and_symbols(
                file_id=file_id_hash,
                path=rel_path,
                git_oid=file_info.git_oid or "",
                content_hash=file_info.content_hash,
                language=file_info.language or "unknown",
                symbols=symbols_list,
            )

        # Pass 2: Create structural edges
        # In a real system, we'd only do this for changed files or their dependents.
        # For recovery, we'll re-process all parse results from this run.
        for file_id, parse_result in all_parse_results:
            file_symbols = self.store.get_symbols_by_file(file_id)
            for imp in parse_result.imports:
                target_name = imp.split(".")[-1]
                target_symbols = self.store.get_symbols_by_name(target_name)
                for ts in target_symbols:
                    for fs in file_symbols:
                        edge_id = stable_hash(
                            {
                                "source": fs["symbol_id"],
                                "target": ts["symbol_id"],
                                "type": "depends_on",
                            }
                        )
                        with self.store.connect() as conn:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO edges (edge_id, source_symbol, target_symbol, edge_type)
                                VALUES (?, ?, ?, 'depends_on')
                            """,
                                (edge_id, fs["symbol_id"], ts["symbol_id"]),
                            )

        # Pass 3: Wiki Generation
        for file_info in scan.files:
            rel_path = file_info.relative_path
            content = (self.settings.repository_path / rel_path).read_text(errors="ignore")

            import hashlib

            file_id_input = rel_path
            file_id_hash = hashlib.sha256(file_id_input.encode()).hexdigest()
            self.wiki.generate_file_wiki(file_id_hash, rel_path, content)

        self.wiki.generate_project_wiki()

        self.store.set_active_commit(git_state.effective_branch, git_state.head_commit or "unknown")

        self.commit_count += 1
        if self.commit_count % 10 == 0:
            import uuid

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

        return git_state.head_commit

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
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        self.initialize_storage()
        is_dirty = False
        try:
            is_dirty = self.git.state().is_dirty
        except Exception:
            pass
        return self.retrieval_engine.retrieve(query, max_tokens=max_tokens, is_dirty=is_dirty)

    def doctor(self) -> dict[str, Any]:
        self.initialize_storage()
        with self.store.connect() as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "database_integrity": integrity,
            "status": self.status().__dict__,
        }
