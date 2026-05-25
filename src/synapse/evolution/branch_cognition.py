from __future__ import annotations

from typing import Any

from synapse.cognition.dag import ContextDag
from synapse.cognition.objects import GraphRelation, SemanticKind
from synapse.evolution.models import (
    CognitiveMergeConflict,
    CognitiveMergeReport,
    MergeConflictKind,
)
from synapse.storage.sqlite import SQLiteEventStore


class CognitiveMergeManager:
    """Manages cognitive merges and divergence analysis between branches."""

    def __init__(self, *, event_store: SQLiteEventStore, dag: ContextDag) -> None:
        self.event_store = event_store
        self.dag = dag

    def detect_conflicts(
        self, left_context_hash: str, right_context_hash: str
    ) -> CognitiveMergeReport:
        """Find the divergence common ancestor and detect semantic conflicts."""
        common = self.dag.divergence(left_context_hash, right_context_hash)

        if not common:
            ancestor_semantics: dict[str, Any] = {}
        else:
            ancestor_semantics = self._reconstruct_semantics(common)

        left_semantics = self._reconstruct_semantics(left_context_hash)
        right_semantics = self._reconstruct_semantics(right_context_hash)

        left_edges = self._reconstruct_edges(left_context_hash)
        right_edges = self._reconstruct_edges(right_context_hash)

        conflicts: list[CognitiveMergeConflict] = []
        all_ids = set(left_semantics.keys()) | set(right_semantics.keys())

        for stable_id in all_ids:
            left_obj = left_semantics.get(stable_id)
            right_obj = right_semantics.get(stable_id)
            anc_obj = ancestor_semantics.get(stable_id)

            if left_obj and right_obj:
                left_changed = (not anc_obj) or (
                    anc_obj["summary"] != left_obj["summary"]
                    or anc_obj["valid_to_context"] != left_obj["valid_to_context"]
                )
                right_changed = (not anc_obj) or (
                    anc_obj["summary"] != right_obj["summary"]
                    or anc_obj["valid_to_context"] != right_obj["valid_to_context"]
                )

                if left_changed and right_changed:
                    if left_obj["summary"] != right_obj["summary"]:
                        conflicts.append(
                            CognitiveMergeConflict(
                                stable_id=stable_id,
                                conflict_type=MergeConflictKind.MODIFY_MODIFY,
                                left_summary=left_obj["summary"],
                                right_summary=right_obj["summary"],
                                description=f"Semantic object '{stable_id}' modified on both branches with differing summaries.",
                                resolution_candidates=(
                                    f"Accept left: {left_obj['summary'][:60]}...",
                                    f"Accept right: {right_obj['summary'][:60]}...",
                                ),
                            )
                        )
                    elif left_obj["valid_to_context"] != right_obj["valid_to_context"]:
                        conflicts.append(
                            CognitiveMergeConflict(
                                stable_id=stable_id,
                                conflict_type=MergeConflictKind.REMOVE_MODIFY,
                                left_summary=(
                                    "Active" if not left_obj["valid_to_context"] else "Invalidated"
                                ),
                                right_summary=(
                                    "Active" if not right_obj["valid_to_context"] else "Invalidated"
                                ),
                                description=f"Semantic object '{stable_id}' has conflicting validity states (left: {left_obj['valid_to_context'] or 'active'}, right: {right_obj['valid_to_context'] or 'active'}).",
                                resolution_candidates=(
                                    "Keep active (valid)",
                                    "Invalidate (retired)",
                                ),
                            )
                        )
            elif left_obj and not right_obj and anc_obj:
                if anc_obj["summary"] != left_obj["summary"]:
                    conflicts.append(
                        CognitiveMergeConflict(
                            stable_id=stable_id,
                            conflict_type=MergeConflictKind.REMOVE_MODIFY,
                            left_summary=left_obj["summary"],
                            right_summary="Deleted/Removed",
                            description=f"Semantic object '{stable_id}' modified on left branch but removed on right branch.",
                            resolution_candidates=(
                                f"Accept left modification: {left_obj['summary'][:60]}...",
                                "Accept right deletion",
                            ),
                        )
                    )
            elif right_obj and not left_obj and anc_obj:
                if anc_obj["summary"] != right_obj["summary"]:
                    conflicts.append(
                        CognitiveMergeConflict(
                            stable_id=stable_id,
                            conflict_type=MergeConflictKind.REMOVE_MODIFY,
                            left_summary="Deleted/Removed",
                            right_summary=right_obj["summary"],
                            description=f"Semantic object '{stable_id}' removed on left branch but modified on right branch.",
                            resolution_candidates=(
                                "Accept left deletion",
                                f"Accept right modification: {right_obj['summary'][:60]}...",
                            ),
                        )
                    )

        # Detect cross-branch assumption conflicts
        for stable_id, left_obj in left_semantics.items():
            if left_obj.get("kind") == SemanticKind.ASSUMPTION.value:
                right_obj = right_semantics.get(stable_id)
                # Check if assumption is active on one branch but retired on the other,
                # and reference edges point to it.
                left_invalidated = left_obj.get("valid_to_context") is not None
                right_invalidated = (
                    right_obj.get("valid_to_context") is not None if right_obj else False
                )

                if left_invalidated and not right_invalidated:
                    has_references = any(
                        e.get("to_id") == stable_id
                        and e.get("relation") in (GraphRelation.REFERENCES.value, "references")
                        for e in right_edges
                    )
                    if has_references:
                        conflicts.append(
                            CognitiveMergeConflict(
                                stable_id=stable_id,
                                conflict_type=MergeConflictKind.ASSUMPTION_CONFLICT,
                                left_summary="Invalidated",
                                right_summary="Referenced & Active",
                                description=(
                                    f"Assumption '{stable_id}' was invalidated on left branch "
                                    "but remains active and referenced on right branch."
                                ),
                                resolution_candidates=(
                                    "Accept invalidation and update referencing modules",
                                    "Keep assumption active and reject invalidation",
                                ),
                            )
                        )
                elif right_invalidated and not left_invalidated:
                    has_references = any(
                        e.get("to_id") == stable_id
                        and e.get("relation") in (GraphRelation.REFERENCES.value, "references")
                        for e in left_edges
                    )
                    if has_references:
                        conflicts.append(
                            CognitiveMergeConflict(
                                stable_id=stable_id,
                                conflict_type=MergeConflictKind.ASSUMPTION_CONFLICT,
                                left_summary="Referenced & Active",
                                right_summary="Invalidated",
                                description=(
                                    f"Assumption '{stable_id}' was invalidated on right branch "
                                    "but remains active and referenced on left branch."
                                ),
                                resolution_candidates=(
                                    "Accept invalidation and update referencing modules",
                                    "Keep assumption active and reject invalidation",
                                ),
                            )
                        )

        return CognitiveMergeReport(
            left_context=left_context_hash,
            right_context=right_context_hash,
            common_ancestor=common,
            conflicts=tuple(conflicts),
            can_auto_merge=len(conflicts) == 0,
        )

    def _reconstruct_semantics(self, context_hash: str) -> dict[str, dict[str, Any]]:
        ordered_ancestry = self.dag.ancestry(context_hash)
        ancestry = set(ordered_ancestry)
        rows = self.event_store.semantic_objects_for_contexts(ordered_ancestry)

        semantics: dict[str, dict[str, Any]] = {}
        for context in reversed(ordered_ancestry):
            for row in rows:
                if str(row["context_hash"]) == context:
                    valid_to = row.get("valid_to_context")
                    if valid_to and str(valid_to) in ancestry:
                        semantics.pop(str(row["stable_id"]), None)
                    else:
                        semantics[str(row["stable_id"])] = dict(row)
        return semantics

    def _reconstruct_edges(self, context_hash: str) -> list[dict[str, Any]]:
        ordered_ancestry = self.dag.ancestry(context_hash)
        ancestry = set(ordered_ancestry)
        rows = self.event_store.graph_edges_for_contexts(ordered_ancestry)

        edges: dict[str, dict[str, Any]] = {}
        for context in reversed(ordered_ancestry):
            for row in rows:
                if str(row["context_hash"]) == context:
                    valid_to = row.get("valid_to_context")
                    if valid_to and str(valid_to) in ancestry:
                        edges.pop(str(row["stable_id"]), None)
                    else:
                        edges[str(row["stable_id"])] = dict(row)
        return list(edges.values())
