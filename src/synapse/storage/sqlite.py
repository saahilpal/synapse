from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from synapse.utils.serialization import stable_hash


class SynapseStore:
    """Deterministic SQLite store for repository symbols and structural relationships."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")

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
                    expires_at INTEGER NOT NULL
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
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_symbol);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_symbol);
                CREATE INDEX IF NOT EXISTS idx_embeddings_symbol ON embeddings(symbol_id);
                CREATE INDEX IF NOT EXISTS idx_lessons_status ON lessons(status);
                CREATE INDEX IF NOT EXISTS idx_checkpoints_branch ON checkpoints(branch);
                CREATE INDEX IF NOT EXISTS idx_activity_branch ON activity(branch);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
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
            conn.execute(
                """
                INSERT INTO files (file_id, path, git_oid, content_hash, language, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    file_id = excluded.file_id,
                    git_oid = excluded.git_oid,
                    content_hash = excluded.content_hash,
                    language = excluded.language,
                    updated_at = excluded.updated_at
                """,
                (file_id, path, git_oid, content_hash, language, now),
            )
            conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
            for sym in symbols:
                conn.execute(
                    """
                    INSERT INTO symbols (symbol_id, file_id, name, kind, start_line, end_line, ast_hash, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym["symbol_id"],
                        file_id,
                        sym["name"],
                        sym["kind"],
                        sym["start_line"],
                        sym["end_line"],
                        sym["ast_hash"],
                        json.dumps(sym.get("metadata") or {}),
                    ),
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
            rows = conn.execute(
                """
                SELECT s.*, f.path as source_path
                FROM symbols s
                JOIN files f ON s.file_id = f.file_id
                WHERE s.name LIKE ?
                """,
                (f"%{name}%",),
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

    def update_lesson(self, lesson_id: str, why_failed: str, status: str) -> None:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE lessons SET why_failed = ?, status = ?, approved_at = ?
                WHERE lesson_id = ?
                """,
                (why_failed, status, now, lesson_id),
            )

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

    def get_lessons(self, status: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE status = ? ORDER BY created_at DESC", (status,)
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

            conn.execute("VACUUM")
