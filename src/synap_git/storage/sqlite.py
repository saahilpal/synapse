from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from synap_git.utils.serialization import stable_hash


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
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")

            # Get current user version
            current_version = conn.execute("PRAGMA user_version").fetchone()[0]

            # Target schema version
            TARGET_VERSION = 2

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
                        purpose TEXT NOT NULL,
                        file_path TEXT,
                        created_at INTEGER NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
                    CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                    CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_symbol);
                    CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_symbol);
                    CREATE INDEX IF NOT EXISTS idx_embeddings_symbol ON embeddings(symbol_id);
                    CREATE INDEX IF NOT EXISTS idx_lessons_status ON lessons(status);
                    CREATE INDEX IF NOT EXISTS idx_checkpoints_branch ON checkpoints(branch);
                    CREATE INDEX IF NOT EXISTS idx_activity_branch ON activity(branch);
                """)
                conn.execute("PRAGMA user_version = 1")
                current_version = 1

            if current_version < 2:
                conn.executescript("""
                    -- Add module_key to files
                    ALTER TABLE files ADD COLUMN module_key TEXT;
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

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            conn.commit()
        except Exception:
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
            if parts and parts[0] in ("src", "lib", "app", "cmd", "pkg"):
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

            # Batch insert into FTS5
            fts_data = [(sym["symbol_id"], sym["name"], sym["kind"]) for sym in symbols]
            conn.executemany(
                "INSERT INTO symbols_fts (symbol_id, name, kind) VALUES (?, ?, ?)",
                fts_data,
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

    def get_symbols_by_name(self, name: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            clean_name = name.replace('"', '""')
            rows = conn.execute(
                """
                SELECT s.*, f.path as source_path
                FROM symbols_fts fts
                JOIN symbols s ON fts.symbol_id = s.symbol_id
                JOIN files f ON s.file_id = f.file_id
                WHERE symbols_fts MATCH ?
                """,
                (f'"{clean_name}"*',),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_neighborhood(self, symbol_id: str, depth: int = 2) -> list[dict[str, Any]]:
        """Use Recursive CTE for SQL-side graph traversal."""
        with self.connect() as conn:
            rows = conn.execute(
                """
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
                )
                SELECT s.*, f.path as source_path, n.d as distance
                FROM symbols s
                JOIN files f ON s.file_id = f.file_id
                JOIN neighborhood n ON s.symbol_id = n.id
                ORDER BY n.d ASC
            """,
                (symbol_id, depth, depth),
            ).fetchall()
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

    def get_decisions(self, branch: str, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE branch = ? ORDER BY created_at DESC LIMIT ?",
                (branch, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_checkpoint(self, branch: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE branch = ? ORDER BY created_at DESC LIMIT 1",
                (branch,),
            ).fetchone()
        return dict(row) if row else None

    def get_checkpoints(self, branch: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE branch = ? ORDER BY created_at DESC",
                (branch,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_checkpoint(self, checkpoint_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            )

    def get_lessons(self, status: str) -> list[dict[str, Any]]:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE status = ? AND expires_at >= ? ORDER BY created_at DESC",
                (status, now),
            ).fetchall()
        return [dict(row) for row in rows]

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
        """Checks DB integrity. If corrupted, deletes SQLite files to force a clean rebuild from Git."""
        try:
            if not self.path.exists():
                return False
            with self.connect() as conn:
                res = conn.execute("PRAGMA quick_check").fetchone()[0]
                if res == "ok":
                    return False
        except Exception:
            pass

        # If we got here, it's corrupted or unreachable. Wipe it securely.
        for ext in ["", "-wal", "-shm"]:
            f = Path(f"{self.path}{ext}")
            if f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass
        return True

    def put_llm_call(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str,
        file_path: str | None = None,
    ) -> None:
        import uuid
        from datetime import UTC

        call_id = str(uuid.uuid4())
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (call_id, provider, model, input_tokens, output_tokens, purpose, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id,
                    provider or "unknown",
                    model or "unknown",
                    input_tokens,
                    output_tokens,
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
            row = conn.execute(
                """
                SELECT * FROM wiki_queue
                WHERE status = 'pending' AND attempts < 5
                ORDER BY created_at ASC LIMIT 1
                """
            ).fetchone()
            if row:
                task_id = row["task_id"]
                conn.execute(
                    """
                    UPDATE wiki_queue
                    SET status = 'processing', updated_at = ?
                    WHERE task_id = ?
                    """,
                    (now, task_id),
                )
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
            conn.execute("DELETE FROM symbols_fts")

        # Run VACUUM outside the transaction context
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=30.0)
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
