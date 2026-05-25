from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.cognition.dag import ContextDag
from synapse.storage.sqlite import SQLiteEventStore
from synapse.temporal.models import EvolutionInterval, TemporalFact


@dataclass(frozen=True)
class TemporalGraphState:
    context_hash: str
    facts: tuple[TemporalFact, ...]


class TemporalGraphEngine:
    """Reconstructs temporally valid cognition facts at a context head."""

    def __init__(self, *, event_store: SQLiteEventStore, dag: ContextDag) -> None:
        self.event_store = event_store
        self.dag = dag

    def reconstruct(self, context_hash: str) -> TemporalGraphState:
        ordered_ancestry = self.dag.ancestry(context_hash)
        ancestry = set(ordered_ancestry)

        # Bulk retrieve all semantic objects in the ancestry to avoid N-query pattern
        all_rows = self.event_store.semantic_objects_for_contexts(ordered_ancestry)

        # Group rows by context_hash for O(1) retrieval
        rows_by_context: dict[str, list[dict[str, Any]]] = {}
        for row in all_rows:
            rows_by_context.setdefault(str(row["context_hash"]), []).append(row)

        facts: dict[str, TemporalFact] = {}
        for context in reversed(ordered_ancestry):
            for row in rows_by_context.get(context, []):
                valid_to = row.get("valid_to_context")
                if valid_to and str(valid_to) in ancestry:
                    facts.pop(str(row["stable_id"]), None)
                    continue
                facts[str(row["stable_id"])] = TemporalFact(
                    stable_id=str(row["stable_id"]),
                    kind=str(row["kind"]),
                    summary=str(row["summary"]),
                    interval=EvolutionInterval(
                        valid_from_context=str(row["context_hash"]),
                        valid_to_context=str(valid_to) if valid_to else None,
                        valid_from_git=row.get("git_commit_hash"),
                        valid_to_git=None,
                    ),
                    metadata={"source_uri": row["source_uri"]},
                )
        return TemporalGraphState(context_hash=context_hash, facts=tuple(facts.values()))
