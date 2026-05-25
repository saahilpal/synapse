from __future__ import annotations

import json
from typing import Any

from synapse.cognition.objects import Snapshot
from synapse.storage.sqlite import SQLiteEventStore


class CognitionCompactor:
    """Handles database compaction, cold storage migration, and replay checkpoints."""

    def __init__(self, event_store: SQLiteEventStore) -> None:
        self.event_store = event_store

    def compact(self) -> dict[str, Any]:
        """Perform full compaction (deduplication + cold migration)."""
        dedup_count = self.deduplicate()
        migration_count = self.migrate_to_cold_storage(limit_commits=100)
        checkpoint_hash = self.create_replay_checkpoint()

        return {
            "deduplicated_records": dedup_count,
            "migrated_contexts": migration_count,
            "checkpoint_hash": checkpoint_hash,
        }

    def deduplicate(self) -> int:
        """Finds and deletes adjacent duplicate semantic object history records.

        If a stable_id has consecutive commits in the history of the context DAG
        with identical summary, kind, confidence, tags, and validity, we keep the first
        and last records and prune the intermediate ones (since they can be reconstructed
        or fetched from cold storage).
        """
        pruned_count = 0
        with self.event_store.connect() as conn:
            rows = conn.execute("SELECT DISTINCT stable_id FROM semantic_objects").fetchall()
            stable_ids = [str(r["stable_id"]) for r in rows]

            for sid in stable_ids:
                history = conn.execute(
                    """
                    SELECT so.*, co.created_at AS context_created_at
                    FROM semantic_objects so
                    JOIN context_objects co ON co.context_hash = so.context_hash
                    WHERE so.stable_id = ?
                    ORDER BY co.created_at ASC
                    """,
                    (sid,),
                ).fetchall()

                if len(history) < 3:
                    continue

                i = 0
                while i < len(history):
                    j = i + 1
                    while j < len(history):
                        same = (
                            history[i]["summary"] == history[j]["summary"]
                            and history[i]["kind"] == history[j]["kind"]
                            and history[i]["confidence"] == history[j]["confidence"]
                            and history[i]["tags_json"] == history[j]["tags_json"]
                            and history[i]["valid_to_context"] == history[j]["valid_to_context"]
                        )
                        if not same:
                            break
                        j += 1

                    if j - i >= 3:
                        for idx in range(i + 1, j - 1):
                            row = history[idx]
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO cold_semantic_objects(
                                    stable_id, context_hash, kind, summary, tags_json, metadata_json,
                                    source_uri, source_hash, git_commit_hash, branch, confidence,
                                    valid_from_context, valid_to_context, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    row["stable_id"],
                                    row["context_hash"],
                                    row["kind"],
                                    row["summary"],
                                    row["tags_json"],
                                    row["metadata_json"],
                                    row["source_uri"],
                                    row["source_hash"],
                                    row["git_commit_hash"],
                                    row["branch"],
                                    row["confidence"],
                                    row["valid_from_context"],
                                    row["valid_to_context"],
                                    row["created_at"],
                                ),
                            )
                            conn.execute(
                                "DELETE FROM semantic_objects WHERE stable_id = ? AND context_hash = ?",
                                (row["stable_id"], row["context_hash"]),
                            )
                            pruned_count += 1
                    i = j
        return pruned_count

    def migrate_to_cold_storage(self, limit_commits: int = 100) -> int:
        """Moves context commits older than the latest `limit_commits` to cold tables.

        Keep active heads and their ancestry, but prune other old states to cold storage.
        """
        with self.event_store.connect() as conn:
            rows = conn.execute(
                "SELECT context_hash FROM context_objects ORDER BY created_at DESC"
            ).fetchall()
            all_hashes = [str(r["context_hash"]) for r in rows]

            if len(all_hashes) <= limit_commits:
                return 0

            head_rows = conn.execute("SELECT context_hash FROM active_heads").fetchall()
            active_heads = {str(r["context_hash"]) for r in head_rows}

            cold_hashes = []
            for h in all_hashes[limit_commits:]:
                if h not in active_heads:
                    cold_hashes.append(h)

            migrated_count = 0
            for ch in cold_hashes:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cold_semantic_objects
                    SELECT * FROM semantic_objects WHERE context_hash = ?
                    """,
                    (ch,),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cold_context_objects
                    SELECT * FROM context_objects WHERE context_hash = ?
                    """,
                    (ch,),
                )

                conn.execute("DELETE FROM semantic_objects WHERE context_hash = ?", (ch,))
                conn.execute("DELETE FROM graph_nodes WHERE context_hash = ?", (ch,))
                conn.execute("DELETE FROM graph_edges WHERE context_hash = ?", (ch,))
                conn.execute("DELETE FROM projection_cache WHERE context_hash = ?", (ch,))
                conn.execute("DELETE FROM context_objects WHERE context_hash = ?", (ch,))
                migrated_count += 1

            return migrated_count

    def create_replay_checkpoint(self) -> str:
        """Create a state snapshot checkpoint to accelerate future replays."""
        max_seq = self.event_store.max_event_sequence()

        with self.event_store.connect() as conn:
            row = conn.execute(
                "SELECT context_hash FROM active_heads ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            context_head = str(row["context_hash"]) if row else None

        object_hashes = self.event_store.object_hashes()
        state_hash = json.dumps(
            {"heads": context_head, "objects_count": len(object_hashes)}, sort_keys=True
        )

        snapshot = Snapshot.create(
            context_head=context_head,
            event_sequence=max_seq,
            state_hash=state_hash,
            object_hashes=tuple(object_hashes),
        )
        self.event_store.append_snapshot(snapshot)
        return snapshot.snapshot_hash
