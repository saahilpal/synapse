from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from synapse.cognition.objects import (
    ContextObject,
    EventRecord,
    EventType,
    GraphEdge,
    GraphNode,
    SemanticObject,
    Snapshot,
    TrustRecord,
)
from synapse.serialization import to_primitive

CURRENT_SCHEMA_VERSION = 5


class SQLiteStoreError(RuntimeError):
    """Raised when SQLite source-of-truth operations fail."""


@dataclass(frozen=True)
class StoreStats:
    events: int
    context_objects: int
    semantic_objects: int
    graph_nodes: int
    graph_edges: int
    snapshots: int
    active_heads: int
    transactions: int


class SQLiteEventStore:
    """Append-only SQLite WAL store plus compact indexes for context projections."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._migrate(conn)

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

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS object_refs (
                object_hash TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                compressed_size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                schema_version INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                actor TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                git_commit_hash TEXT,
                branch TEXT,
                observed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS context_objects (
                context_hash TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                git_commit_hash TEXT,
                branch TEXT,
                event_sequence INTEGER,
                object_hash TEXT NOT NULL,
                summary TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(event_sequence) REFERENCES events(sequence)
            );

            CREATE TABLE IF NOT EXISTS context_edges (
                child_hash TEXT NOT NULL,
                parent_hash TEXT NOT NULL,
                edge_type TEXT NOT NULL DEFAULT 'parent',
                PRIMARY KEY (child_hash, parent_hash, edge_type)
            );

            CREATE TABLE IF NOT EXISTS active_heads (
                branch TEXT PRIMARY KEY,
                context_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(context_hash) REFERENCES context_objects(context_hash)
            );

            CREATE TABLE IF NOT EXISTS semantic_objects (
                stable_id TEXT NOT NULL,
                context_hash TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                source_hash TEXT,
                git_commit_hash TEXT,
                branch TEXT,
                confidence REAL NOT NULL,
                valid_from_context TEXT,
                valid_to_context TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (stable_id, context_hash),
                FOREIGN KEY(context_hash) REFERENCES context_objects(context_hash)
            );

            CREATE TABLE IF NOT EXISTS graph_nodes (
                stable_id TEXT NOT NULL,
                context_hash TEXT NOT NULL,
                node_type TEXT NOT NULL,
                labels_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                confidence REAL NOT NULL,
                valid_from_context TEXT,
                valid_to_context TEXT,
                PRIMARY KEY (stable_id, context_hash),
                FOREIGN KEY(context_hash) REFERENCES context_objects(context_hash)
            );

            CREATE TABLE IF NOT EXISTS graph_edges (
                stable_id TEXT NOT NULL,
                context_hash TEXT NOT NULL,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                confidence REAL NOT NULL,
                valid_from_context TEXT,
                valid_to_context TEXT,
                PRIMARY KEY (stable_id, context_hash),
                FOREIGN KEY(context_hash) REFERENCES context_objects(context_hash)
            );

            CREATE TABLE IF NOT EXISTS trust_records (
                source TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                trust_level TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                rationale TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_hash TEXT PRIMARY KEY,
                context_head TEXT,
                event_sequence INTEGER NOT NULL,
                state_hash TEXT NOT NULL,
                object_hashes_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projection_state (
                projection_name TEXT PRIMARY KEY,
                context_head TEXT,
                state_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cognition_transactions (
                transaction_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                event_sequence INTEGER,
                context_hash TEXT,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS transaction_objects (
                transaction_id TEXT NOT NULL,
                object_hash TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (transaction_id, object_hash),
                FOREIGN KEY(transaction_id) REFERENCES cognition_transactions(transaction_id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_observed_at ON events(observed_at);
            CREATE INDEX IF NOT EXISTS idx_events_git_commit ON events(git_commit_hash);
            CREATE INDEX IF NOT EXISTS idx_context_git_commit ON context_objects(git_commit_hash);
            CREATE INDEX IF NOT EXISTS idx_context_branch ON context_objects(branch);
            CREATE INDEX IF NOT EXISTS idx_semantic_kind ON semantic_objects(kind);
            CREATE INDEX IF NOT EXISTS idx_semantic_source ON semantic_objects(source_uri);
            CREATE INDEX IF NOT EXISTS idx_semantic_stable_id ON semantic_objects(stable_id);
            CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_graph_edges_relation ON graph_edges(relation);
            CREATE INDEX IF NOT EXISTS idx_transactions_status
                ON cognition_transactions(status);
            CREATE INDEX IF NOT EXISTS idx_transaction_objects_hash
                ON transaction_objects(object_hash);
            """
        )

        if current_version < 4:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projection_cache (
                    context_hash TEXT NOT NULL,
                    projection_kind TEXT NOT NULL,
                    filters_hash TEXT NOT NULL,
                    graph_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (context_hash, projection_kind, filters_hash),
                    FOREIGN KEY(context_hash) REFERENCES context_objects(context_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_semantic_context_hash ON semantic_objects(context_hash);
                CREATE INDEX IF NOT EXISTS idx_graph_nodes_context_hash ON graph_nodes(context_hash);
                CREATE INDEX IF NOT EXISTS idx_graph_edges_context_hash ON graph_edges(context_hash);
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (4, datetime.now(UTC).isoformat()),
            )
            conn.execute("PRAGMA user_version=4")

        # Reload version for sequential upgrades
        cursor = conn.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]

        if current_version < 5:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cold_context_objects (
                    context_hash TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    git_commit_hash TEXT,
                    branch TEXT,
                    event_sequence INTEGER,
                    object_hash TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cold_semantic_objects (
                    stable_id TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    source_hash TEXT,
                    git_commit_hash TEXT,
                    branch TEXT,
                    confidence REAL NOT NULL,
                    valid_from_context TEXT,
                    valid_to_context TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (stable_id, context_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_projection_cache_lookup 
                    ON projection_cache(context_hash, projection_kind, filters_hash);
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (5, datetime.now(UTC).isoformat()),
            )
            conn.execute("PRAGMA user_version=5")

    def record_object_ref(
        self,
        *,
        object_hash: str,
        kind: str,
        schema_version: int,
        size_bytes: int,
        compressed_size_bytes: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO object_refs(
                    object_hash, kind, schema_version, size_bytes, compressed_size_bytes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (object_hash, kind, schema_version, size_bytes, compressed_size_bytes),
            )

    def append_event(self, event: EventRecord) -> EventRecord:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO events(
                    event_id, schema_version, event_type, source, actor, payload_hash,
                    correlation_id, git_commit_hash, branch, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_id),
                    event.schema_version,
                    event.event_type.value,
                    event.source,
                    event.actor,
                    event.payload_hash,
                    event.correlation_id,
                    event.git_commit_hash,
                    event.branch,
                    event.observed_at.isoformat(),
                ),
            )
            row = conn.execute(
                "SELECT sequence FROM events WHERE event_id = ?",
                (str(event.event_id),),
            ).fetchone()
            if row is None:
                raise SQLiteStoreError(f"event insert failed: {event.event_id}")
            return event.with_sequence(int(row["sequence"]))

    def get_event_by_sequence(self, sequence: int) -> EventRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE sequence = ?",
                (sequence,),
            ).fetchone()
        if row is None:
            return None
        return EventRecord(
            event_id=UUID(str(row["event_id"])),
            sequence=int(row["sequence"]),
            event_type=EventType(str(row["event_type"])),
            source=str(row["source"]),
            payload_hash=str(row["payload_hash"]),
            actor=str(row["actor"]),
            correlation_id=str(row["correlation_id"]),
            git_commit_hash=row["git_commit_hash"],
            branch=row["branch"],
            observed_at=datetime.fromisoformat(str(row["observed_at"])),
            schema_version=int(row["schema_version"]),
        )

    def start_transaction(
        self,
        *,
        transaction_id: str,
        idempotency_key: str,
        operation: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO cognition_transactions(
                    transaction_id, idempotency_key, operation, status, started_at, updated_at
                ) VALUES (?, ?, ?, 'in_progress', ?, ?)
                """,
                (transaction_id, idempotency_key, operation, now, now),
            )
            row = conn.execute(
                "SELECT * FROM cognition_transactions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            raise SQLiteStoreError(f"transaction insert failed: {transaction_id}")
        return dict(row)

    def record_transaction_object(
        self,
        *,
        transaction_id: str,
        object_hash: str,
        kind: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO transaction_objects(
                    transaction_id, object_hash, kind, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (transaction_id, object_hash, kind, datetime.now(UTC).isoformat()),
            )

    def finish_transaction(
        self,
        *,
        transaction_id: str,
        status: str,
        event_sequence: int | None = None,
        context_hash: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE cognition_transactions
                SET status = ?, event_sequence = ?, context_hash = ?, error_message = ?,
                    updated_at = ?
                WHERE transaction_id = ?
                """,
                (
                    status,
                    event_sequence,
                    context_hash,
                    error_message,
                    datetime.now(UTC).isoformat(),
                    transaction_id,
                ),
            )

    def transaction_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM cognition_transactions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return None if row is None else dict(row)

    def list_transactions(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM cognition_transactions ORDER BY started_at ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM cognition_transactions
                    WHERE status = ?
                    ORDER BY started_at ASC
                    """,
                    (status,),
                ).fetchall()
        return [dict(row) for row in rows]

    def append_context_object(self, context: ContextObject) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO context_objects(
                    context_hash, schema_version, git_commit_hash, branch, event_sequence,
                    object_hash, summary, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context.object_hash,
                    context.schema_version,
                    context.git_commit_hash,
                    context.branch,
                    context.event_sequence,
                    context.object_hash,
                    context.summary,
                    context.confidence.score,
                    context.created_at.isoformat(),
                ),
            )
            for parent_hash in context.parent_hashes:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO context_edges(child_hash, parent_hash, edge_type)
                    VALUES (?, ?, 'parent')
                    """,
                    (context.object_hash, parent_hash),
                )
            self._insert_semantic_objects(conn, context.object_hash, context.semantic_delta)
            self._insert_graph_nodes(conn, context.object_hash, context.graph_nodes)
            self._insert_graph_edges(conn, context.object_hash, context.graph_edges)

    def _insert_semantic_objects(
        self,
        conn: sqlite3.Connection,
        context_hash: str,
        objects: Iterable[SemanticObject],
    ) -> None:
        for semantic in objects:
            conn.execute(
                """
                INSERT OR IGNORE INTO semantic_objects(
                    stable_id, context_hash, kind, summary, tags_json, metadata_json,
                    source_uri, source_hash, git_commit_hash, branch, confidence,
                    valid_from_context, valid_to_context, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    semantic.stable_id,
                    context_hash,
                    semantic.kind.value,
                    semantic.summary,
                    json.dumps(list(semantic.tags), sort_keys=True),
                    json.dumps(to_primitive(semantic.metadata), sort_keys=True),
                    semantic.provenance.source_uri,
                    semantic.provenance.source_hash,
                    semantic.provenance.git_commit,
                    semantic.provenance.branch,
                    semantic.confidence.score,
                    semantic.validity.valid_from_context,
                    semantic.validity.valid_to_context,
                    semantic.created_at.isoformat(),
                ),
            )

    def _insert_graph_nodes(
        self,
        conn: sqlite3.Connection,
        context_hash: str,
        nodes: Iterable[GraphNode],
    ) -> None:
        for node in nodes:
            conn.execute(
                """
                INSERT OR IGNORE INTO graph_nodes(
                    stable_id, context_hash, node_type, labels_json, metadata_json,
                    source_uri, confidence, valid_from_context, valid_to_context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.stable_id,
                    context_hash,
                    node.node_type.value,
                    json.dumps(list(node.labels), sort_keys=True),
                    json.dumps(to_primitive(node.metadata), sort_keys=True),
                    node.provenance.source_uri,
                    node.confidence.score,
                    node.validity.valid_from_context,
                    node.validity.valid_to_context,
                ),
            )

    def _insert_graph_edges(
        self,
        conn: sqlite3.Connection,
        context_hash: str,
        edges: Iterable[GraphEdge],
    ) -> None:
        for edge in edges:
            conn.execute(
                """
                INSERT OR IGNORE INTO graph_edges(
                    stable_id, context_hash, from_id, to_id, relation, metadata_json,
                    source_uri, confidence, valid_from_context, valid_to_context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge.stable_id,
                    context_hash,
                    edge.from_id,
                    edge.to_id,
                    edge.relation.value,
                    json.dumps(to_primitive(edge.metadata), sort_keys=True),
                    edge.provenance.source_uri,
                    edge.confidence.score,
                    edge.validity.valid_from_context,
                    edge.validity.valid_to_context,
                ),
            )

    def set_active_head(self, *, branch: str, context_hash: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO active_heads(branch, context_hash, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(branch) DO UPDATE SET
                    context_hash = excluded.context_hash,
                    updated_at = excluded.updated_at
                """,
                (branch, context_hash, datetime.now(UTC).isoformat()),
            )

    def get_active_head(self, branch: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT context_hash FROM active_heads WHERE branch = ?",
                (branch,),
            ).fetchone()
        return None if row is None else str(row["context_hash"])

    def context_exists(self, context_hash: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM context_objects WHERE context_hash = ?
                UNION ALL
                SELECT 1 FROM cold_context_objects WHERE context_hash = ?
                """,
                (context_hash, context_hash),
            ).fetchone()
        return row is not None

    def get_context_row(self, context_hash: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_objects WHERE context_hash = ?",
                (context_hash,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM cold_context_objects WHERE context_hash = ?",
                    (context_hash,),
                ).fetchone()
        return cast(sqlite3.Row | None, row)

    def iter_events(self, *, after_sequence: int = 0) -> list[EventRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE sequence > ?
                ORDER BY sequence ASC
                """,
                (after_sequence,),
            ).fetchall()
        events: list[EventRecord] = []
        for row in rows:
            events.append(
                EventRecord(
                    event_id=UUID(str(row["event_id"])),
                    sequence=int(row["sequence"]),
                    event_type=EventType(str(row["event_type"])),
                    source=str(row["source"]),
                    payload_hash=str(row["payload_hash"]),
                    actor=str(row["actor"]),
                    correlation_id=str(row["correlation_id"]),
                    git_commit_hash=row["git_commit_hash"],
                    branch=row["branch"],
                    observed_at=datetime.fromisoformat(str(row["observed_at"])),
                    schema_version=int(row["schema_version"]),
                )
            )
        return events

    def list_context_commits(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT context_hash, git_commit_hash, branch, event_sequence, summary,
                       confidence, created_at
                FROM context_objects
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_context_rows(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM context_objects
                ORDER BY created_at ASC, context_hash ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_context_edges(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM context_edges
                ORDER BY child_hash ASC, parent_hash ASC, edge_type ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_active_heads(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM active_heads
                ORDER BY branch ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def parent_hashes(self, context_hash: str) -> tuple[str, ...]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT parent_hash FROM context_edges
                WHERE child_hash = ? AND edge_type = 'parent'
                ORDER BY parent_hash ASC
                """,
                (context_hash,),
            ).fetchall()
        return tuple(str(row["parent_hash"]) for row in rows)

    def child_hashes(self, context_hash: str) -> tuple[str, ...]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT child_hash FROM context_edges
                WHERE parent_hash = ? AND edge_type = 'parent'
                ORDER BY child_hash ASC
                """,
                (context_hash,),
            ).fetchall()
        return tuple(str(row["child_hash"]) for row in rows)

    def semantic_objects_for_context(self, context_hash: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM semantic_objects WHERE context_hash = ?
                UNION ALL
                SELECT * FROM cold_semantic_objects WHERE context_hash = ?
                ORDER BY stable_id ASC
                """,
                (context_hash, context_hash),
            ).fetchall()
        return [dict(row) for row in rows]

    def semantic_objects_for_contexts(self, context_hashes: Iterable[str]) -> list[dict[str, Any]]:
        hashes = list(context_hashes)
        if not hashes:
            return []
        placeholders = ",".join("?" for _ in hashes)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM semantic_objects WHERE context_hash IN ({placeholders})
                UNION ALL
                SELECT * FROM cold_semantic_objects WHERE context_hash IN ({placeholders})
                ORDER BY stable_id ASC
                """,
                hashes + hashes,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_cached_projection(
        self, context_hash: str, projection_kind: str, filters_hash: str
    ) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT graph_json FROM projection_cache
                WHERE context_hash = ? AND projection_kind = ? AND filters_hash = ?
                """,
                (context_hash, projection_kind, filters_hash),
            ).fetchone()
        return None if row is None else str(row["graph_json"])

    def cache_projection(
        self, context_hash: str, projection_kind: str, filters_hash: str, graph_json: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO projection_cache(
                    context_hash, projection_kind, filters_hash, graph_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    context_hash,
                    projection_kind,
                    filters_hash,
                    graph_json,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def clear_projection_cache(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM projection_cache")

    def graph_nodes_for_context(self, context_hash: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM graph_nodes
                WHERE context_hash = ?
                ORDER BY stable_id ASC
                """,
                (context_hash,),
            ).fetchall()
        return [dict(row) for row in rows]

    def graph_nodes_for_contexts(self, context_hashes: Iterable[str]) -> list[dict[str, Any]]:
        hashes = list(context_hashes)
        if not hashes:
            return []
        placeholders = ",".join("?" for _ in hashes)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM graph_nodes
                WHERE context_hash IN ({placeholders})
                ORDER BY stable_id ASC
                """,
                hashes,
            ).fetchall()
        return [dict(row) for row in rows]

    def graph_edges_for_context(self, context_hash: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM graph_edges
                WHERE context_hash = ?
                ORDER BY stable_id ASC
                """,
                (context_hash,),
            ).fetchall()
        return [dict(row) for row in rows]

    def graph_edges_for_contexts(self, context_hashes: Iterable[str]) -> list[dict[str, Any]]:
        hashes = list(context_hashes)
        if not hashes:
            return []
        placeholders = ",".join("?" for _ in hashes)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM graph_edges
                WHERE context_hash IN ({placeholders})
                ORDER BY stable_id ASC
                """,
                hashes,
            ).fetchall()
        return [dict(row) for row in rows]

    def search_semantic_objects(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{query}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM semantic_objects
                WHERE summary LIKE ? OR tags_json LIKE ? OR source_uri LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def semantic_history(self, stable_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT so.*, co.event_sequence, co.git_commit_hash AS context_git_commit,
                       co.created_at AS context_created_at
                FROM semantic_objects so
                JOIN context_objects co ON co.context_hash = so.context_hash
                WHERE so.stable_id = ?
                ORDER BY co.event_sequence ASC, co.created_at ASC
                """,
                (stable_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def semantic_objects_by_kind(
        self,
        *,
        kind: str,
        context_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if context_hash:
                rows = conn.execute(
                    """
                    SELECT * FROM semantic_objects
                    WHERE kind = ? AND context_hash = ?
                    ORDER BY stable_id ASC
                    """,
                    (kind, context_hash),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM semantic_objects
                    WHERE kind = ?
                    ORDER BY created_at ASC, stable_id ASC
                    """,
                    (kind,),
                ).fetchall()
        return [dict(row) for row in rows]

    def invalidate_semantic_object(
        self,
        *,
        stable_id: str,
        context_hash: str,
        valid_to_context: str,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE semantic_objects
                SET valid_to_context = ?
                WHERE stable_id = ? AND context_hash = ? AND valid_to_context IS NULL
                """,
                (valid_to_context, stable_id, context_hash),
            )
            return int(cursor.rowcount)

    def append_trust_record(self, trust: TrustRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO trust_records(
                    source, source_type, trust_level, verification_status, rationale,
                    updated_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    source_type = excluded.source_type,
                    trust_level = excluded.trust_level,
                    verification_status = excluded.verification_status,
                    rationale = excluded.rationale,
                    updated_at = excluded.updated_at,
                    schema_version = excluded.schema_version
                """,
                (
                    trust.source,
                    trust.source_type.value,
                    trust.trust_level.value,
                    trust.verification_status.value,
                    trust.rationale,
                    trust.updated_at.isoformat(),
                    trust.schema_version,
                ),
            )

    def append_snapshot(self, snapshot: Snapshot) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO snapshots(
                    snapshot_hash, context_head, event_sequence, state_hash,
                    object_hashes_json, created_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_hash,
                    snapshot.context_head,
                    snapshot.event_sequence,
                    snapshot.state_hash,
                    json.dumps(list(snapshot.object_hashes), sort_keys=True),
                    snapshot.created_at.isoformat(),
                    snapshot.schema_version,
                ),
            )

    def latest_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM snapshots
                ORDER BY event_sequence DESC, created_at DESC
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else dict(row)

    def object_hashes(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT object_hash FROM object_refs ORDER BY object_hash ASC"
            ).fetchall()
        return [str(row["object_hash"]) for row in rows]

    def max_event_sequence(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS max_sequence FROM events"
            ).fetchone()
        return int(row["max_sequence"])

    def stats(self) -> StoreStats:
        with self.connect() as conn:

            def count(table: str) -> int:
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                return int(row["count"])

            return StoreStats(
                events=count("events"),
                context_objects=count("context_objects"),
                semantic_objects=count("semantic_objects"),
                graph_nodes=count("graph_nodes"),
                graph_edges=count("graph_edges"),
                snapshots=count("snapshots"),
                active_heads=count("active_heads"),
                transactions=count("cognition_transactions"),
            )

    def health(self) -> dict[str, Any]:
        with self.connect() as conn:
            user_version = conn.execute("PRAGMA user_version").fetchone()[0]
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        stats = self.stats()
        return {
            "path": self.path.as_posix(),
            "schema_version": int(user_version),
            "journal_mode": str(journal_mode),
            "integrity": str(integrity),
            "stats": stats.__dict__,
        }
