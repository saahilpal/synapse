from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from synap_git.diagnostics.logger import get_logger

logger = get_logger("global_memory")


class GlobalMemoryStore:
    """Manages cross-repository global developer habits and preferences.

    Stored strictly at ~/.synap/global_memory.db with zero automatic leakage into
    repository context prompts (ADR-004).
    """

    DEFAULT_DB_PATH = Path.home() / ".synap" / "global_memory.db"

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path if db_path is not None else self.DEFAULT_DB_PATH
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS global_memories (
                    global_id TEXT PRIMARY KEY,
                    context_key TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT,
                    tags TEXT,
                    fingerprint_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_global_category ON global_memories(category);
                CREATE INDEX IF NOT EXISTS idx_global_fingerprint ON global_memories(fingerprint_hash);
                """
            )

    @staticmethod
    def _compute_fingerprint(context_key: str, content: str) -> str:
        h = hashlib.sha256()
        h.update(context_key.strip().lower().encode("utf-8"))
        h.update(content.strip().encode("utf-8"))
        return h.hexdigest()[:16]

    def add_memory(
        self,
        context_key: str,
        content: str,
        category: str = "habit",
        summary: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add or update a global developer memory."""
        clean_key = context_key.strip()
        clean_content = content.strip()
        if not clean_key or not clean_content:
            raise ValueError("Both context_key and content are required.")

        now = int(time.time())
        fingerprint = self._compute_fingerprint(clean_key, clean_content)
        tags_json = json.dumps(tags or [])
        global_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            # Check existing by key
            existing = conn.execute(
                "SELECT global_id, usage_count FROM global_memories WHERE context_key = ?",
                (clean_key,),
            ).fetchone()
            if existing:
                gid = str(existing["global_id"])
                usage = int(existing["usage_count"])
                conn.execute(
                    """
                    UPDATE global_memories
                    SET category = ?, content = ?, summary = ?, tags = ?,
                        fingerprint_hash = ?, updated_at = ?
                    WHERE global_id = ?
                    """,
                    (category, clean_content, summary.strip(), tags_json, fingerprint, now, gid),
                )
                return {
                    "global_id": gid,
                    "context_key": clean_key,
                    "category": category,
                    "content": clean_content,
                    "summary": summary.strip(),
                    "tags": tags or [],
                    "updated_at": now,
                    "usage_count": usage,
                }
            else:
                conn.execute(
                    """
                    INSERT INTO global_memories (
                        global_id, context_key, category, content, summary,
                        tags, fingerprint_hash, created_at, updated_at, usage_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        global_id,
                        clean_key,
                        category,
                        clean_content,
                        summary.strip(),
                        tags_json,
                        fingerprint,
                        now,
                        now,
                    ),
                )
                return {
                    "global_id": global_id,
                    "context_key": clean_key,
                    "category": category,
                    "content": clean_content,
                    "summary": summary.strip(),
                    "tags": tags or [],
                    "created_at": now,
                    "updated_at": now,
                    "usage_count": 0,
                }

    def list_memories(
        self,
        query: str = "",
        tag: str = "",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List global memories matching optional query text and tag."""
        sql = "SELECT * FROM global_memories WHERE 1=1"
        params: list[Any] = []

        if query.strip():
            q_pat = f"%{query.strip()}%"
            sql += " AND (context_key LIKE ? OR content LIKE ? OR summary LIKE ?)"
            params.extend([q_pat, q_pat, q_pat])

        if tag.strip():
            t_pat = f"%{tag.strip()}%"
            sql += " AND tags LIKE ?"
            params.append(t_pat)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            results: list[dict[str, Any]] = []
            for r in rows:
                tag_list: list[str] = []
                if r["tags"]:
                    try:
                        tag_list = json.loads(r["tags"])
                    except Exception:
                        pass
                results.append(
                    {
                        "global_id": r["global_id"],
                        "context_key": r["context_key"],
                        "category": r["category"],
                        "content": r["content"],
                        "summary": r["summary"] or "",
                        "tags": tag_list,
                        "fingerprint_hash": r["fingerprint_hash"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "usage_count": r["usage_count"],
                    }
                )
            return results

    def get_memory(self, global_id: str) -> dict[str, Any] | None:
        """Retrieve a single global memory by ID."""
        with self._get_connection() as conn:
            r = conn.execute(
                "SELECT * FROM global_memories WHERE global_id = ?",
                (global_id.strip(),),
            ).fetchone()
            if not r:
                return None
            tag_list: list[str] = []
            if r["tags"]:
                try:
                    tag_list = json.loads(r["tags"])
                except Exception:
                    pass
            return {
                "global_id": r["global_id"],
                "context_key": r["context_key"],
                "category": r["category"],
                "content": r["content"],
                "summary": r["summary"] or "",
                "tags": tag_list,
                "fingerprint_hash": r["fingerprint_hash"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "usage_count": r["usage_count"],
            }

    def record_usage(self, global_id: str) -> None:
        """Increment usage counter when a global memory is referenced or ingested."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE global_memories SET usage_count = usage_count + 1 WHERE global_id = ?",
                (global_id.strip(),),
            )
