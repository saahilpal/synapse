from __future__ import annotations

import json
from typing import Any

from synapse.replay.models import (
    ReconstructedLineage,
    ReplayDiagnostic,
    ReplayDiagnosticLevel,
    ReplayResult,
    ReplayTraceEvent,
)
from synapse.serialization import stable_hash
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


class ReplayEngine:
    """Deterministically reconstructs and verifies source-of-truth cognition state."""

    def __init__(self, *, event_store: SQLiteEventStore, object_store: ObjectStore) -> None:
        self.event_store = event_store
        self.object_store = object_store

    def replay(self, *, after_sequence: int = 0, use_checkpoint: bool = True) -> ReplayResult:
        checkpoint = self.event_store.latest_snapshot() if use_checkpoint else None
        checkpoint_sequence = _checkpoint_sequence(checkpoint)
        start_sequence = max(after_sequence, checkpoint_sequence or 0)
        events = self.event_store.iter_events(after_sequence=start_sequence)
        context_rows = self.event_store.list_context_rows()
        edge_rows = self.event_store.list_context_edges()
        active_heads = self.event_store.list_active_heads()

        diagnostics: list[ReplayDiagnostic] = []
        trace: list[ReplayTraceEvent] = []
        context_hashes = {str(row["context_hash"]) for row in context_rows}

        for event in events:
            try:
                self.object_store.verify(event.payload_hash)
            except Exception as exc:
                diagnostics.append(
                    ReplayDiagnostic(
                        level=ReplayDiagnosticLevel.ERROR.value,
                        message=f"event payload verification failed: {exc}",
                        object_id=event.payload_hash,
                    )
                )
                status = "error"
            else:
                status = "ok"
            trace.append(
                ReplayTraceEvent(
                    sequence=event.sequence,
                    operation=event.event_type.value,
                    object_id=event.payload_hash,
                    status=status,
                    detail={
                        "event_id": str(event.event_id),
                        "branch": event.branch,
                        "git_commit_hash": event.git_commit_hash,
                    },
                )
            )

        lineage: list[ReconstructedLineage] = []
        for row in context_rows:
            context_hash = str(row["context_hash"])
            try:
                self.object_store.verify(context_hash)
            except Exception as exc:
                diagnostics.append(
                    ReplayDiagnostic(
                        level=ReplayDiagnosticLevel.ERROR.value,
                        message=f"context object verification failed: {exc}",
                        object_id=context_hash,
                    )
                )
            parents = tuple(
                str(edge["parent_hash"])
                for edge in edge_rows
                if str(edge["child_hash"]) == context_hash
            )
            missing = tuple(parent for parent in parents if parent not in context_hashes)
            for parent in missing:
                diagnostics.append(
                    ReplayDiagnostic(
                        level=ReplayDiagnosticLevel.ERROR.value,
                        message=f"context parent is missing: {parent}",
                        object_id=context_hash,
                    )
                )
            lineage.append(
                ReconstructedLineage(
                    context_hash=context_hash,
                    parent_hashes=parents,
                    git_commit_hash=_nullable_str(row.get("git_commit_hash")),
                    branch=_nullable_str(row.get("branch")),
                    event_sequence=_nullable_int(row.get("event_sequence")),
                )
            )

        for head in active_heads:
            context_hash = str(head["context_hash"])
            if context_hash not in context_hashes:
                diagnostics.append(
                    ReplayDiagnostic(
                        level=ReplayDiagnosticLevel.ERROR.value,
                        message=f"active head points to missing context: {context_hash}",
                        object_id=str(head["branch"]),
                    )
                )

        state_payload: dict[str, Any] = {
            "checkpoint_sequence": checkpoint_sequence,
            "events": [
                {
                    "sequence": event.sequence,
                    "event_id": str(event.event_id),
                    "event_type": event.event_type.value,
                    "payload_hash": event.payload_hash,
                }
                for event in events
            ],
            "lineage": [
                {
                    "context_hash": item.context_hash,
                    "parent_hashes": item.parent_hashes,
                    "git_commit_hash": item.git_commit_hash,
                    "branch": item.branch,
                    "event_sequence": item.event_sequence,
                }
                for item in lineage
            ],
            "active_heads": active_heads,
        }
        return ReplayResult(
            event_count=len(events),
            context_count=len(lineage),
            state_hash=stable_hash(state_payload),
            diagnostics=tuple(diagnostics),
            trace=tuple(trace),
            lineage=tuple(lineage),
            checkpoint_sequence=checkpoint_sequence,
        )


def _checkpoint_sequence(row: dict[str, Any] | None) -> int | None:
    if row is None:
        return None
    value = row.get("event_sequence")
    if value is None:
        return None
    return int(value)


def _nullable_str(value: object) -> str | None:
    return None if value is None else str(value)


def _nullable_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def decode_snapshot_object_hashes(row: dict[str, Any]) -> tuple[str, ...]:
    value = json.loads(str(row["object_hashes_json"]))
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)
