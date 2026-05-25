from __future__ import annotations

import json
import re
from typing import Any

from synapse.assumptions.models import AssumptionRecord, AssumptionStatus
from synapse.cognition.objects import SemanticKind
from synapse.evolution.engine import CognitiveEvolutionEngine
from synapse.storage.sqlite import SQLiteEventStore

DEPENDENCY_HINT_RE = re.compile(
    r"\b(redis|postgres|postgresql|sqlite|qdrant|neo4j|kafka|rabbitmq)\b",
    re.I,
)


class AssumptionEngine:
    """Tracks explicit/inferred assumptions and marks stale assumptions over time."""

    def __init__(
        self,
        *,
        event_store: SQLiteEventStore,
        evolution: CognitiveEvolutionEngine,
    ) -> None:
        self.event_store = event_store
        self.evolution = evolution

    def list_assumptions(self, *, context_hash: str | None = None) -> tuple[AssumptionRecord, ...]:
        rows = self.event_store.semantic_objects_by_kind(
            kind=SemanticKind.ASSUMPTION.value,
            context_hash=context_hash,
        )
        return tuple(self._record(row) for row in rows)

    def invalidated_between(
        self,
        *,
        left_context: str,
        right_context: str,
        apply: bool = False,
    ) -> tuple[AssumptionRecord, ...]:
        diff = self.evolution.semantic_diff(left_context, right_context)
        removed_ids = {item.stable_id for item in diff.removed}
        left_assumptions = self.event_store.semantic_objects_by_kind(
            kind=SemanticKind.ASSUMPTION.value,
            context_hash=left_context,
        )
        right_dependencies = _dependency_names(
            self.event_store.semantic_objects_by_kind(
                kind=SemanticKind.DEPENDENCY.value,
                context_hash=right_context,
            )
        )
        invalidated: list[AssumptionRecord] = []
        for row in left_assumptions:
            reason = self._invalidation_reason(row, removed_ids, right_dependencies)
            if not reason:
                continue
            if apply:
                self.event_store.invalidate_semantic_object(
                    stable_id=str(row["stable_id"]),
                    context_hash=left_context,
                    valid_to_context=right_context,
                )
            invalidated.append(
                self._record(
                    row,
                    status=AssumptionStatus.INVALIDATED,
                    invalidated_by_context=right_context,
                    invalidation_reason=reason,
                )
            )
        return tuple(invalidated)

    def _invalidation_reason(
        self,
        row: dict[str, Any],
        removed_ids: set[str],
        current_dependencies: set[str],
    ) -> str | None:
        stable_id = str(row["stable_id"])
        summary = str(row["summary"]).lower()
        for match in DEPENDENCY_HINT_RE.finditer(summary):
            dependency = match.group(1).lower()
            normalized = "postgresql" if dependency == "postgres" else dependency
            if normalized not in current_dependencies:
                return f"referenced dependency no longer appears active: {normalized}"
        if stable_id in removed_ids:
            return "assumption semantic object disappeared in target context"
        source_uri = str(row["source_uri"])
        if source_uri and source_uri not in {"manual://note"} and row.get("valid_to_context"):
            return "source validity window is closed"
        return None

    def _record(
        self,
        row: dict[str, Any],
        *,
        status: AssumptionStatus | None = None,
        invalidated_by_context: str | None = None,
        invalidation_reason: str | None = None,
    ) -> AssumptionRecord:
        inferred_status = status
        if inferred_status is None:
            inferred_status = (
                AssumptionStatus.INVALIDATED
                if row.get("valid_to_context")
                else AssumptionStatus.ACTIVE
            )
        return AssumptionRecord(
            stable_id=str(row["stable_id"]),
            context_hash=str(row["context_hash"]),
            status=inferred_status,
            summary=str(row["summary"]),
            source_uri=str(row["source_uri"]),
            confidence=float(row["confidence"]),
            invalidated_by_context=invalidated_by_context or row.get("valid_to_context"),
            invalidation_reason=invalidation_reason,
            metadata=_metadata(row),
        )


def _dependency_names(rows: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for row in rows:
        metadata = _metadata(row)
        dependencies = metadata.get("dependencies", [])
        if isinstance(dependencies, list):
            names.update(str(dependency).lower() for dependency in dependencies)
    return names


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(row.get("metadata_json", "{}")))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
