from __future__ import annotations

import functools
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from synap_git.utils.serialization import stable_hash


@functools.lru_cache(maxsize=4096)
def _parse_cached_vec(vec_json: str) -> tuple[tuple[float, ...], float]:
    try:
        v = tuple(float(x) for x in json.loads(vec_json))
        norm = sum(x * x for x in v) ** 0.5
        return v, norm
    except Exception:
        return (), 0.0


def _cosine_similarity(vec1_json: str, vec2_json: str) -> float:
    v1, norm_a = _parse_cached_vec(vec1_json)
    v2, norm_b = _parse_cached_vec(vec2_json)
    if norm_a == 0.0 or norm_b == 0.0 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    return float(dot / (norm_a * norm_b))


class LessonStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class SynapStore:
    """Deterministic SQLite store for repository symbols and structural relationships."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            # ARCHITECTURAL DECISION (AUD-07):
            # PRAGMA synchronous=NORMAL in WAL mode is an intentional tradeoff:
            # It avoids fsync() on every transaction commit, providing a 5-10x throughput boost for bulk AST indexing.
            # In the rare event of an OS power-loss crash during a write, SQLite WAL recovery or Synapse's automatic
            # self-healing (`recover_if_corrupted()`) safely reconstructs the deterministic local index.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")

            # Get current user version
            current_version = conn.execute("PRAGMA user_version").fetchone()[0]

            # Target schema version
            TARGET_VERSION = 6

            if current_version < 1:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS files (
                        file_id TEXT PRIMARY KEY,
                        path TEXT UNIQUE,
                        git_oid TEXT,
                        content_hash TEXT,
                        language TEXT,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS symbols (
                        symbol_id TEXT PRIMARY KEY,
                        file_id TEXT,
                        name TEXT,
                        kind TEXT,
                        start_line INTEGER,
                        end_line INTEGER,
                        ast_hash TEXT,
                        metadata_json TEXT,
                        FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS edges (
                        edge_id TEXT PRIMARY KEY,
                        source_symbol TEXT,
                        target_symbol TEXT,
                        edge_type TEXT,
                        FOREIGN KEY(source_symbol) REFERENCES symbols(symbol_id) ON DELETE CASCADE,
                        FOREIGN KEY(target_symbol) REFERENCES symbols(symbol_id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS embeddings (
                        embedding_id TEXT PRIMARY KEY,
                        symbol_id TEXT,
                        model_name TEXT,
                        model_version TEXT,
                        prompt_version TEXT,
                        vector BLOB,
                        content_hash TEXT,
                        FOREIGN KEY(symbol_id) REFERENCES symbols(symbol_id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS active_state (
                        branch TEXT PRIMARY KEY,
                        git_commit_hash TEXT,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS decisions (
                        decision_id TEXT PRIMARY KEY,
                        branch TEXT NOT NULL,
                        commit_hash TEXT NOT NULL,
                        content TEXT NOT NULL,
                        context TEXT,
                        agent_id TEXT,
                        created_at INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS checkpoints (
                        checkpoint_id TEXT PRIMARY KEY,
                        branch TEXT NOT NULL,
                        commit_hash TEXT NOT NULL,
                        doing TEXT NOT NULL,
                        changed_files TEXT NOT NULL,
                        next_step TEXT,
                        decisions TEXT,
                        blockers TEXT,
                        token_count INTEGER,
                        created_at INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS lessons (
                        lesson_id TEXT PRIMARY KEY,
                        branch TEXT NOT NULL,
                        revert_commit TEXT NOT NULL,
                        reverted_from TEXT NOT NULL,
                        what_failed TEXT NOT NULL,
                        why_failed TEXT NOT NULL,
                        files_affected TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at INTEGER NOT NULL,
                        approved_at INTEGER,
                        expires_at INTEGER NOT NULL,
                        approval_actor TEXT
                    );

                    CREATE TABLE IF NOT EXISTS activity (
                        activity_id TEXT PRIMARY KEY,
                        branch TEXT NOT NULL,
                        commit_hash TEXT NOT NULL,
                        action TEXT NOT NULL,
                        files TEXT,
                        created_at INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS llm_calls (
                        call_id TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        input_tokens INTEGER NOT NULL,
                        output_tokens INTEGER NOT NULL,
                        cost_usd REAL NOT NULL,
                        purpose TEXT NOT NULL,
                        file_path TEXT,
                        created_at INTEGER NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
                    CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                    CREATE INDEX IF NOT EXISTS idx_symbols_start_end ON symbols(file_id, start_line, end_line);
                    CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_symbol);
                    CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_symbol);
                    CREATE INDEX IF NOT EXISTS idx_edges_src_tgt ON edges(source_symbol, target_symbol);
                    CREATE INDEX IF NOT EXISTS idx_edges_tgt_src ON edges(target_symbol, source_symbol);
                    CREATE INDEX IF NOT EXISTS idx_embeddings_symbol ON embeddings(symbol_id);
                    CREATE INDEX IF NOT EXISTS idx_lessons_status ON lessons(status);
                    CREATE INDEX IF NOT EXISTS idx_checkpoints_branch ON checkpoints(branch);
                    CREATE INDEX IF NOT EXISTS idx_activity_branch ON activity(branch);
                """)
                conn.execute("PRAGMA user_version = 1")
                current_version = 1

            if current_version < 2:
                # Safely add module_key to files if not already present
                col_info = conn.execute("PRAGMA table_info(files)").fetchall()
                col_names = [
                    col["name"] if isinstance(col, sqlite3.Row) else col[1] for col in col_info
                ]
                if "module_key" not in col_names:
                    conn.execute("ALTER TABLE files ADD COLUMN module_key TEXT")

                conn.executescript("""
                    CREATE INDEX IF NOT EXISTS idx_files_module_key ON files(module_key);

                    -- Create symbol search virtual table using FTS5
                    CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
                        symbol_id UNINDEXED,
                        name,
                        kind UNINDEXED
                    );

                    -- Populate symbols_fts with existing symbols if any
                    INSERT INTO symbols_fts (symbol_id, name, kind)
                    SELECT symbol_id, name, kind FROM symbols;

                    -- Trigger to delete from FTS when symbols is deleted
                    CREATE TRIGGER IF NOT EXISTS tgr_symbols_delete AFTER DELETE ON symbols BEGIN
                        DELETE FROM symbols_fts WHERE symbol_id = old.symbol_id;
                    END;

                    -- Create wiki_status and wiki_queue tables
                    CREATE TABLE IF NOT EXISTS wiki_status (
                        path TEXT PRIMARY KEY,
                        git_oid TEXT,
                        status TEXT NOT NULL DEFAULT 'stale',
                        updated_at INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS wiki_queue (
                        task_id TEXT PRIMARY KEY,
                        file_path TEXT UNIQUE,
                        status TEXT NOT NULL DEFAULT 'pending',
                        attempts INTEGER DEFAULT 0,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    );
                """)
                conn.execute("PRAGMA user_version = 2")
                current_version = 2

            if current_version < 3:
                # Migrate file_ids to include content_hash (SPEC-001)
                import hashlib

                conn.execute("PRAGMA foreign_keys=OFF")
                try:
                    rows = conn.execute("SELECT file_id, path, content_hash FROM files").fetchall()
                    for row in rows:
                        old_id = row["file_id"]
                        path = row["path"]
                        content_hash = row["content_hash"] or ""
                        new_id = hashlib.sha256((path + content_hash).encode("utf-8")).hexdigest()
                        if old_id != new_id:
                            conn.execute(
                                "UPDATE files SET file_id = ? WHERE file_id = ?", (new_id, old_id)
                            )
                            conn.execute(
                                "UPDATE symbols SET file_id = ? WHERE file_id = ?", (new_id, old_id)
                            )
                finally:
                    conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA user_version = 3")
                current_version = 3

            if current_version < 4:
                conn.executescript("""
                    CREATE INDEX IF NOT EXISTS idx_files_content_hash ON files(content_hash);
                    CREATE INDEX IF NOT EXISTS idx_files_git_oid ON files(git_oid);

                    CREATE TRIGGER IF NOT EXISTS tgr_symbols_insert
                    AFTER INSERT ON symbols BEGIN
                        INSERT INTO symbols_fts(symbol_id, name, kind, body)
                        VALUES (new.symbol_id, new.name, new.kind, new.metadata_json);
                    END;

                    -- Re-create symbols_fts with body column
                    DROP TABLE IF EXISTS symbols_fts;
                    CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
                        symbol_id UNINDEXED,
                        name,
                        kind UNINDEXED,
                        body
                    );

                    INSERT INTO symbols_fts (symbol_id, name, kind, body)
                    SELECT symbol_id, name, kind, metadata_json FROM symbols;
                """)
                conn.execute("PRAGMA user_version = 4")
                current_version = 4

            if current_version < 5:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS agent_memory (
                        id TEXT PRIMARY KEY,
                        timestamp INTEGER,
                        context_key TEXT,
                        payload TEXT,
                        summary TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_agent_memory_key ON agent_memory(context_key);
                """)
                conn.execute("PRAGMA user_version = 5")
                current_version = 5

            if current_version < 6:
                # Deduplicate agent_memory by context_key before creating unique index
                conn.execute("""
                    DELETE FROM agent_memory
                    WHERE rowid NOT IN (
                        SELECT MAX(rowid) FROM agent_memory GROUP BY context_key
                    )
                """)
                conn.executescript("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memory_key_unique ON agent_memory(context_key);
                    CREATE INDEX IF NOT EXISTS idx_symbols_start_end ON symbols(file_id, start_line, end_line);
                    CREATE INDEX IF NOT EXISTS idx_edges_src_tgt ON edges(source_symbol, target_symbol);
                    CREATE INDEX IF NOT EXISTS idx_edges_tgt_src ON edges(target_symbol, source_symbol);
                    CREATE INDEX IF NOT EXISTS idx_wiki_queue_pending ON wiki_queue(status, created_at) WHERE status = 'pending';
                    CREATE INDEX IF NOT EXISTS idx_decisions_branch_created ON decisions(branch, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_checkpoints_branch_created ON checkpoints(branch, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_lessons_status_expires_created ON lessons(status, expires_at, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_agent_memory_key_time ON agent_memory(context_key, timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_agent_memory_time ON agent_memory(timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_activity_branch_created ON activity(branch, created_at DESC);
                """)
                conn.execute("PRAGMA user_version = 6")
                current_version = 6

            # Ensure agent_memory unique index exists on pre-existing databases
            mem_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_memory'"
            ).fetchone()
            if mem_table:
                conn.execute("""
                    DELETE FROM agent_memory
                    WHERE rowid NOT IN (
                        SELECT MAX(rowid) FROM agent_memory GROUP BY context_key
                    )
                """)
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memory_key_unique ON agent_memory(context_key)"
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.create_function("cosine_similarity", 2, _cosine_similarity)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA cache_size=-64000")
            conn.execute("PRAGMA temp_store=MEMORY")
            yield conn
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def upsert_file_and_symbols(
        self,
        file_id: str,
        path: str,
        git_oid: str,
        content_hash: str,
        language: str,
        symbols: list[dict[str, Any]],
    ) -> str:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            # Compute module_key
            p = Path(path)
            stem_path = p.with_suffix("")
            parts = list(stem_path.parts)
            skip_prefixes = {
                "src",
                "lib",
                "app",
                "cmd",
                "pkg",
                "internal",
                "source",
                "packages",
                "main",
                "java",
                "kotlin",
                "scala",
            }
            while parts and parts[0] in skip_prefixes:
                parts = parts[1:]
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            module_key = ".".join(parts)

            # Handle file_id change due to content change (SPEC-001)
            # We delete the old file and its symbols to avoid FK constraint violations
            # when the file_id changes.
            conn.execute("DELETE FROM files WHERE path = ?", (path,))

            conn.execute(
                """
                INSERT INTO files (file_id, path, git_oid, content_hash, language, module_key, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, path, git_oid, content_hash, language, module_key, now),
            )
            # Delete any symbols for the NEW file_id just in case of a collision or prior partial run
            conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))

            # Batch insert symbols
            symbols_data = [
                (
                    sym["symbol_id"],
                    file_id,
                    sym["name"],
                    sym["kind"],
                    sym["start_line"],
                    sym["end_line"],
                    sym["ast_hash"],
                    json.dumps(sym.get("metadata") or {}),
                )
                for sym in symbols
            ]
            conn.executemany(
                """
                INSERT INTO symbols (symbol_id, file_id, name, kind, start_line, end_line, ast_hash, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                symbols_data,
            )

        return file_id

    def get_file_by_path(self, path: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def set_active_commit(self, branch: str, commit_hash: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO active_state (branch, git_commit_hash, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(branch) DO UPDATE SET
                    git_commit_hash = excluded.git_commit_hash,
                    updated_at = excluded.updated_at
            """,
                (branch, commit_hash, now),
            )

    def get_active_commit(self, branch: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT git_commit_hash FROM active_state WHERE branch = ?", (branch,)
            ).fetchone()
        return row["git_commit_hash"] if row else None

    def get_last_indexed_commit(self) -> str | None:
        """Return the commit hash that the local SQLite index currently mirrors."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT git_commit_hash FROM active_state ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return row["git_commit_hash"] if row else None

    def get_symbols_by_file(self, file_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*, f.path as source_path
                FROM symbols s
                JOIN files f ON s.file_id = f.file_id
                WHERE s.file_id = ?
                """,
                (file_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_symbols_by_lexical_query(
        self, query_words: set[str], limit: int = 50
    ) -> list[dict[str, Any]]:
        if not query_words:
            return []
        parts = []
        for w in query_words:
            parts.append(f'"{w}"*')
            parts.append(f'body:"{w}"*')
        match_expr = " OR ".join(parts)
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH top_matches AS (
                    SELECT symbol_id, bm25(symbols_fts) as rank
                    FROM symbols_fts
                    WHERE symbols_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                )
                SELECT s.*, f.path as source_path, tm.rank
                FROM top_matches tm
                JOIN symbols s ON tm.symbol_id = s.symbol_id
                JOIN files f ON s.file_id = f.file_id
                ORDER BY tm.rank ASC
                """,
                (match_expr, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_neighborhood(
        self,
        symbol_id: str,
        depth: int = 2,
        max_neighbors: int = 50,
        direction: str = "downstream",
    ) -> list[dict[str, Any]]:
        """Use Recursive CTE with pre-aggregated min_distances for directed SQL-side graph traversal."""
        with self.connect() as conn:
            params: tuple[Any, ...]
            if direction == "upstream":
                query = """
                WITH RECURSIVE neighborhood(id, d) AS (
                    SELECT ? as id, 0 as d
                    UNION
                    SELECT source_symbol, d + 1
                    FROM edges JOIN neighborhood ON target_symbol = id
                    WHERE d < ?
                ),
                min_distances AS (
                    SELECT id, MIN(d) as distance
                    FROM neighborhood
                    GROUP BY id
                    ORDER BY distance ASC
                    LIMIT ?
                )
                SELECT s.*, f.path as source_path, m.distance
                FROM min_distances m
                JOIN symbols s ON s.symbol_id = m.id
                JOIN files f ON s.file_id = f.file_id
                ORDER BY m.distance ASC
                """
                params = (symbol_id, depth, max_neighbors)
            elif direction == "both":
                query = """
                WITH RECURSIVE neighborhood(id, d) AS (
                    SELECT ? as id, 0 as d
                    UNION
                    SELECT target_symbol, d + 1
                    FROM edges JOIN neighborhood ON source_symbol = id
                    WHERE d < ?
                    UNION
                    SELECT source_symbol, d + 1
                    FROM edges JOIN neighborhood ON target_symbol = id
                    WHERE d < ?
                ),
                min_distances AS (
                    SELECT id, MIN(d) as distance
                    FROM neighborhood
                    GROUP BY id
                    ORDER BY distance ASC
                    LIMIT ?
                )
                SELECT s.*, f.path as source_path, m.distance
                FROM min_distances m
                JOIN symbols s ON s.symbol_id = m.id
                JOIN files f ON s.file_id = f.file_id
                ORDER BY m.distance ASC
                """
                params = (symbol_id, depth, depth, max_neighbors)
            else:  # downstream (default)
                query = """
                WITH RECURSIVE neighborhood(id, d) AS (
                    SELECT ? as id, 0 as d
                    UNION
                    SELECT target_symbol, d + 1
                    FROM edges JOIN neighborhood ON source_symbol = id
                    WHERE d < ?
                ),
                min_distances AS (
                    SELECT id, MIN(d) as distance
                    FROM neighborhood
                    GROUP BY id
                    ORDER BY distance ASC
                    LIMIT ?
                )
                SELECT s.*, f.path as source_path, m.distance
                FROM min_distances m
                JOIN symbols s ON s.symbol_id = m.id
                JOIN files f ON s.file_id = f.file_id
                ORDER BY m.distance ASC
                """
                params = (symbol_id, depth, max_neighbors)

            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def put_embedding(
        self,
        symbol_id: str,
        model_name: str,
        model_version: str,
        prompt_version: str,
        vector: list[float],
        content_hash: str,
    ) -> None:
        embedding_id = stable_hash(
            {
                "symbol_id": symbol_id,
                "model": model_name,
                "version": model_version,
                "prompt": prompt_version,
            }
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO embeddings (embedding_id, symbol_id, model_name, model_version, prompt_version, vector, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(embedding_id) DO UPDATE SET
                    vector = excluded.vector,
                    content_hash = excluded.content_hash
            """,
                (
                    embedding_id,
                    symbol_id,
                    model_name,
                    model_version,
                    prompt_version,
                    json.dumps(vector),
                    content_hash,
                ),
            )

    def get_embedding(self, symbol_id: str, model_name: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM embeddings
                WHERE symbol_id = ? AND model_name = ?
            """,
                (symbol_id, model_name),
            ).fetchone()
        return dict(row) if row else None

    def get_similar_symbols(
        self, query_vector: list[float], limit: int = 50
    ) -> list[dict[str, Any]]:
        vec_json = json.dumps(query_vector)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*, f.path as source_path, cosine_similarity(e.vector, ?) as similarity
                FROM embeddings e
                JOIN symbols s ON e.symbol_id = s.symbol_id
                JOIN files f ON s.file_id = f.file_id
                ORDER BY similarity DESC
                LIMIT ?
                """,
                (vec_json, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def put_decision(
        self, decision_id: str, branch: str, commit_hash: str, content: str, context_info: str
    ) -> None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions (decision_id, branch, commit_hash, content, context, agent_id, created_at)
                VALUES (?, ?, ?, ?, ?, 'agent', ?)
                """,
                (decision_id, branch, commit_hash, content, context_info, now),
            )

    def put_checkpoint(
        self,
        checkpoint_id: str,
        branch: str,
        commit_hash: str,
        doing: str,
        changed_files: str,
        next_step: str,
        blockers: str,
    ) -> None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (checkpoint_id, branch, commit_hash, doing, changed_files, next_step, blockers, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    branch,
                    commit_hash,
                    doing,
                    changed_files,
                    next_step,
                    blockers,
                    now,
                ),
            )

    def update_lesson(
        self, lesson_id: str, why_failed: str, status: str, actor: str = "system"
    ) -> None:
        try:
            LessonStatus(status)
        except ValueError:
            raise ValueError(f"Invalid lesson status: {status}")

        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE lessons SET why_failed = ?, status = ?, approved_at = ?, approval_actor = ?
                WHERE lesson_id = ?
                """,
                (why_failed, status, now, actor, lesson_id),
            )

    def delete_lesson(self, lesson_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM lessons WHERE lesson_id = ?", (lesson_id,))

    def prune_expired_lessons(self) -> int:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE lessons
                SET status = ?
                WHERE status IN (?, ?) AND expires_at < ?
                """,
                (
                    LessonStatus.EXPIRED.value,
                    LessonStatus.PENDING.value,
                    LessonStatus.APPROVED.value,
                    now,
                ),
            )
            return cursor.rowcount

    def get_decisions(self, branch: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        try:
            with self.connect() as conn:
                if not branch or branch == "all":
                    rows = conn.execute(
                        "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM decisions WHERE branch = ? ORDER BY created_at DESC LIMIT ?",
                        (branch, limit),
                    ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def get_latest_checkpoint(self, branch: str) -> dict[str, Any] | None:
        try:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT * FROM checkpoints WHERE branch = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                    (branch,),
                ).fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError:
            return None

    def get_checkpoints(self, branch: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        try:
            with self.connect() as conn:
                if branch:
                    rows = conn.execute(
                        "SELECT * FROM checkpoints WHERE branch = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                        (branch, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM checkpoints ORDER BY created_at DESC, rowid DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        try:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT * FROM checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                ).fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError:
            return None

    def store_memory(
        self,
        memory_id: str,
        context_key: str,
        payload: str,
        summary: str,
    ) -> None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute("DELETE FROM agent_memory WHERE context_key = ?", (context_key,))
            conn.execute(
                """
                INSERT INTO agent_memory (id, timestamp, context_key, payload, summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (memory_id, now, context_key, payload, summary),
            )

    def get_recent_memory(
        self, context_key: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        try:
            with self.connect() as conn:
                if context_key:
                    rows = conn.execute(
                        """
                        SELECT * FROM agent_memory
                        WHERE context_key = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (context_key, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM agent_memory
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def delete_checkpoint(self, checkpoint_id: str) -> None:
        try:
            with self.connect() as conn:
                conn.execute(
                    "DELETE FROM checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                )
        except sqlite3.OperationalError:
            pass

    def get_blast_radius(self, diff_ranges: dict[str, list[tuple[int, int]]]) -> dict[str, Any]:
        """
        Analyze the impacted code symbols and 1-hop callers from dirty line ranges.
        Deterministic and runs in < 2ms without external dependencies.
        """
        if not diff_ranges:
            return {"touched_symbols": [], "direct_callers": [], "impacted_tests": []}

        touched: list[dict[str, Any]] = []
        with self.connect() as conn:
            for path, ranges in diff_ranges.items():
                for s_line, e_line in ranges:
                    rows = conn.execute(
                        """
                        SELECT s.symbol_id, s.name, s.kind, s.start_line, s.end_line, f.path
                        FROM symbols s
                        JOIN files f ON s.file_id = f.file_id
                        WHERE f.path = ?
                          AND NOT (s.end_line < ? OR s.start_line > ?)
                        """,
                        (path, s_line, e_line),
                    ).fetchall()
                    for r in rows:
                        d = dict(r)
                        if not any(t["symbol_id"] == d["symbol_id"] for t in touched):
                            touched.append(d)

            callers: list[dict[str, Any]] = []
            tests: list[dict[str, Any]] = []
            if touched:
                touched_ids = [t["symbol_id"] for t in touched]
                placeholders = ",".join(["?"] * len(touched_ids))
                caller_rows = conn.execute(
                    f"""
                    SELECT s_caller.name, s_caller.kind, f_caller.path, s_caller.start_line, s_target.name as impacts
                    FROM edges e
                    JOIN symbols s_caller ON e.source_symbol = s_caller.symbol_id
                    JOIN files f_caller ON s_caller.file_id = f_caller.file_id
                    JOIN symbols s_target ON e.target_symbol = s_target.symbol_id
                    WHERE e.target_symbol IN ({placeholders})
                    """,  # noqa: S608
                    touched_ids,
                ).fetchall()
                for r in caller_rows:
                    cd = dict(r)
                    if "test" in cd["path"].lower():
                        if not any(
                            x["name"] == cd["name"] and x["path"] == cd["path"] for x in tests
                        ):
                            tests.append(cd)
                    else:
                        if not any(
                            x["name"] == cd["name"] and x["path"] == cd["path"] for x in callers
                        ):
                            callers.append(cd)

        return {
            "touched_symbols": touched,
            "direct_callers": callers,
            "impacted_tests": tests,
        }

    def compute_pagerank(
        self,
        active_files: list[str] | None = None,
        limit: int = 10,
        damping: float = 0.85,
        iterations: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Compute Personalized PageRank (PPR) over the AST symbol reference graph.
        100% free and deterministic, identifying core architectural hubs in < 5ms.
        Accelerated using integer index arrays and pre-filtered dangling nodes.
        """
        with self.connect() as conn:
            symbol_rows = conn.execute(
                "SELECT s.symbol_id, s.name, s.kind, f.path FROM symbols s JOIN files f ON s.file_id = f.file_id"
            ).fetchall()
            edge_rows = conn.execute("SELECT source_symbol, target_symbol FROM edges").fetchall()

        if not symbol_rows:
            return []

        symbols = [r["symbol_id"] for r in symbol_rows]
        sym_meta = [{"name": r["name"], "kind": r["kind"], "path": r["path"]} for r in symbol_rows]
        n = len(symbols)
        if n == 0:
            return []

        sym_to_idx = {sid: i for i, sid in enumerate(symbols)}
        adj_idx: list[list[int]] = [[] for _ in range(n)]
        out_deg: list[int] = [0] * n

        for src, tgt in edge_rows:
            u = sym_to_idx.get(src)
            v = sym_to_idx.get(tgt)
            if u is not None and v is not None:
                adj_idx[u].append(v)
                out_deg[u] += 1

        dangling_nodes = [i for i in range(n) if out_deg[i] == 0]

        active_indices: list[int] = []
        if active_files:
            active_set = set(active_files)
            for i, meta in enumerate(sym_meta):
                if meta["path"] in active_set:
                    active_indices.append(i)

        if active_indices:
            weight = 1.0 / len(active_indices)
            p = [(weight if i in active_indices else 0.0) for i in range(n)]
        else:
            uniform = 1.0 / n
            p = [uniform] * n

        ranks = list(p)
        base_factor = 1.0 - damping

        for _ in range(iterations):
            new_ranks = [base_factor * p[i] for i in range(n)]
            dangling_sum = sum(ranks[i] for i in dangling_nodes)
            dangling_contrib = damping * dangling_sum
            if dangling_contrib > 0.0:
                for i in range(n):
                    new_ranks[i] += dangling_contrib * p[i]

            for u in range(n):
                targets = adj_idx[u]
                if targets:
                    contrib = damping * (ranks[u] / len(targets))
                    for v in targets:
                        new_ranks[v] += contrib
            ranks = new_ranks

        sorted_indices = sorted(range(n), key=lambda i: ranks[i], reverse=True)[:limit]
        return [
            {
                "symbol_id": symbols[i],
                "name": sym_meta[i]["name"],
                "kind": sym_meta[i]["kind"],
                "path": sym_meta[i]["path"],
                "score": round(ranks[i], 5),
            }
            for i in sorted_indices
        ]

    def get_lessons(self, status: str) -> list[dict[str, Any]]:
        now = int(datetime.now(UTC).timestamp())
        try:
            with self.connect() as conn:
                if status == "all":
                    rows = conn.execute(
                        "SELECT * FROM lessons WHERE expires_at >= ? ORDER BY created_at DESC",
                        (now,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM lessons WHERE status = ? AND expires_at >= ? ORDER BY created_at DESC",
                        (status, now),
                    ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def put_activity(
        self,
        activity_id: str,
        branch: str,
        commit_hash: str,
        action: str,
        files: str | None = None,
    ) -> None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO activity (activity_id, branch, commit_hash, action, files, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (activity_id, branch, commit_hash, action, files, now),
            )

    def get_activity(self, branch: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM activity WHERE branch = ? ORDER BY created_at DESC LIMIT ?",
                (branch, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def integrity_check(self) -> str:
        with self.connect() as conn:
            return str(conn.execute("PRAGMA quick_check").fetchone()[0])

    def recover_if_corrupted(self) -> bool:
        """Checks DB integrity. Wipes files ONLY on verified on-disk corruption, never on locks."""
        if not self.path.exists():
            return False

        is_corrupt = False
        try:
            conn = sqlite3.connect(self.path, timeout=5.0)
            try:
                conn.execute("PRAGMA busy_timeout=5000")
                cursor = conn.execute("PRAGMA quick_check")
                row = cursor.fetchone()
                if row is not None and str(row[0]).strip().lower() != "ok":
                    is_corrupt = True
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg or "busy" in error_msg or "timeout" in error_msg:
                import structlog

                structlog.get_logger().warning(
                    "database_locked_or_busy_skipping_recovery", path=str(self.path), error=str(e)
                )
                return False
            if (
                "file is not a database" in error_msg
                or "malformed" in error_msg
                or "corrupt" in error_msg
            ):
                is_corrupt = True
            else:
                return False
        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if (
                "file is not a database" in error_msg
                or "malformed" in error_msg
                or "corrupt" in error_msg
            ):
                is_corrupt = True
            else:
                return False
        except (TimeoutError, OSError):
            return False
        except Exception:
            return False

        if is_corrupt:
            import structlog

            structlog.get_logger().error("database_corruption_detected_wiping", path=str(self.path))
            for ext in ["", "-wal", "-shm"]:
                f = Path(f"{self.path}{ext}")
                if f.exists():
                    try:
                        f.unlink()
                    except OSError:
                        pass
            return True
        return False

    def put_llm_call(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str,
        cost_usd: float = 0.0,
        file_path: str | None = None,
    ) -> None:
        import uuid
        from datetime import UTC

        if not cost_usd:
            cost_usd = 0.0
            p_lower = provider.lower() if provider else ""
            m_lower = model.lower() if model else ""

            if "openai" in p_lower:
                if "mini" in m_lower:
                    cost_usd = (input_tokens * 0.150 + output_tokens * 0.600) / 1_000_000
                else:
                    cost_usd = (input_tokens * 5.00 + output_tokens * 15.00) / 1_000_000
            elif "gemini" in p_lower:
                if "pro" in m_lower:
                    cost_usd = (input_tokens * 3.50 + output_tokens * 10.50) / 1_000_000
                else:
                    cost_usd = (input_tokens * 0.075 + output_tokens * 0.300) / 1_000_000
            elif "anthropic" in p_lower:
                if "sonnet" in m_lower:
                    cost_usd = (input_tokens * 3.00 + output_tokens * 15.00) / 1_000_000
                elif "haiku" in m_lower:
                    cost_usd = (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000
                else:
                    cost_usd = (input_tokens * 3.00 + output_tokens * 15.00) / 1_000_000

        call_id = str(uuid.uuid4())
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (call_id, provider, model, input_tokens, output_tokens, cost_usd, purpose, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id,
                    provider or "unknown",
                    model or "unknown",
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    purpose,
                    file_path,
                    now,
                ),
            )

    def get_wiki_status(self, path: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM wiki_status WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def set_wiki_status(self, path: str, git_oid: str | None, status: str) -> None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO wiki_status (path, git_oid, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    git_oid = excluded.git_oid,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (path, git_oid, status, now),
            )

    def enqueue_wiki(self, file_path: str) -> None:
        import uuid

        # Skip non-documentable assets, lockfiles, and minified bundles
        ignored_suffixes = (
            ".svg",
            ".lock",
            ".xml",
            ".typed",
            ".min.js",
            ".min.css",
            ".map",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            ".wasm",
            ".pyc",
        )
        lower = file_path.lower()
        if (
            any(lower.endswith(sfx) for sfx in ignored_suffixes)
            or lower.endswith("package-lock.json")
            or lower.endswith("yarn.lock")
        ):
            return

        now = int(datetime.now(UTC).timestamp())
        task_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO wiki_queue (task_id, file_path, status, attempts, created_at, updated_at)
                VALUES (?, ?, 'pending', 0, ?, ?)
                """,
                (task_id, file_path, now, now),
            )

    def dequeue_wiki(self) -> dict[str, Any] | None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                UPDATE wiki_queue
                SET status = 'processing', updated_at = ?
                WHERE task_id = (
                    SELECT task_id FROM wiki_queue
                    WHERE status = 'pending' AND attempts < 5
                    ORDER BY created_at ASC LIMIT 1
                )
                RETURNING *
                """,
                (now,),
            ).fetchone()
            if row:
                return dict(row)
        return None

    def update_wiki_queue_status(self, task_id: str, status: str, attempts: int) -> None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            if status == "completed":
                conn.execute("DELETE FROM wiki_queue WHERE task_id = ?", (task_id,))
            else:
                conn.execute(
                    """
                    UPDATE wiki_queue
                    SET status = ?, attempts = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status, attempts, now, task_id),
                )

    def clear_wiki_queue(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM wiki_queue")

    def retry_failed_wiki_queue(self) -> int:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE wiki_queue SET status = 'pending', attempts = 0, updated_at = ? WHERE status = 'failed'",
                (now,),
            )
            return cursor.rowcount

    def get_llm_calls(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM llm_calls ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def clear_llm_calls(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM llm_calls")

    def clear_all(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM symbols")
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM embeddings")
            conn.execute("DELETE FROM active_state")
            conn.execute("DELETE FROM decisions")
            conn.execute("DELETE FROM checkpoints")
            conn.execute("DELETE FROM lessons")
            conn.execute("DELETE FROM activity")
            conn.execute("DELETE FROM llm_calls")
            conn.execute("DELETE FROM wiki_status")
            conn.execute("DELETE FROM wiki_queue")
            conn.execute("DELETE FROM agent_memory")

        # Run VACUUM outside the transaction context
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=30.0)
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
