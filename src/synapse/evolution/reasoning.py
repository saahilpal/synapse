from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from synapse.cognition.dag import ContextDag
from synapse.cognition.objects import GraphNodeType, GraphRelation, SemanticKind
from synapse.evolution.models import (
    AssumptionConsequence,
    CouplingChange,
    DomainErosionItem,
    ReasoningReport,
    SemanticDriftItem,
)
from synapse.storage.sqlite import SQLiteEventStore


class CognitiveReasoningEngine:
    """Performs deep cognitive and architectural reasoning over temporal states."""

    def __init__(self, *, event_store: SQLiteEventStore, dag: ContextDag) -> None:
        self.event_store = event_store
        self.dag = dag

    def analyze_reasoning(self, context_hash: str) -> ReasoningReport:
        """Analyze semantic evolution, coupling, drift, and assumption impacts."""
        # 1. Fetch current graph and semantic context
        current_nodes = self.event_store.graph_nodes_for_context(context_hash)
        current_edges = self.event_store.graph_edges_for_context(context_hash)
        current_semantics = self.event_store.semantic_objects_for_context(context_hash)

        # 2. Identify parent context for diffs
        parent_hashes = self.event_store.parent_hashes(context_hash)
        parent_hash = parent_hashes[0] if parent_hashes else None

        parent_nodes: list[dict[str, Any]] = []
        parent_edges: list[dict[str, Any]] = []
        parent_semantics: list[dict[str, Any]] = []
        if parent_hash:
            parent_nodes = self.event_store.graph_nodes_for_context(parent_hash)
            parent_edges = self.event_store.graph_edges_for_context(parent_hash)
            parent_semantics = self.event_store.semantic_objects_for_context(parent_hash)

        # A. Coupling Changes Analysis
        coupling_changes = self._analyze_coupling(
            current_nodes, current_edges, parent_nodes, parent_edges
        )

        # B. Semantic Drift Analysis
        semantic_drift = self._analyze_drift(current_semantics, parent_semantics, context_hash)

        # C. Domain Erosion Analysis
        domain_erosion = self._analyze_domain_erosion(
            current_nodes, current_edges, current_semantics
        )

        # D. Assumption Consequences
        assumption_consequences = self._analyze_assumption_consequences(
            current_nodes, current_edges, current_semantics
        )

        return ReasoningReport(
            context_hash=context_hash,
            coupling_changes=tuple(coupling_changes),
            semantic_drift=tuple(semantic_drift),
            domain_erosion=tuple(domain_erosion),
            assumption_consequences=tuple(assumption_consequences),
        )

    def _analyze_coupling(
        self,
        current_nodes: list[dict[str, Any]],
        current_edges: list[dict[str, Any]],
        parent_nodes: list[dict[str, Any]],
        parent_edges: list[dict[str, Any]],
    ) -> list[CouplingChange]:
        changes: list[CouplingChange] = []

        # Calculate efferent (outgoing) and afferent (incoming) depends_on edges
        def get_coupling(
            nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
        ) -> dict[str, tuple[int, int]]:
            module_ids = {
                n["stable_id"]
                for n in nodes
                if n["node_type"] in (GraphNodeType.MODULE.value, GraphNodeType.PACKAGE.value)
            }
            coupling: dict[str, tuple[int, int]] = dict.fromkeys(module_ids, (0, 0))
            for edge in edges:
                rel = edge.get("relation")
                if rel in (GraphRelation.DEPENDS_ON.value, "depends_on"):
                    from_id = edge.get("from_id")
                    to_id = edge.get("to_id")
                    if from_id in coupling:
                        eff, aff = coupling[from_id]
                        coupling[from_id] = (eff + 1, aff)
                    if to_id in coupling:
                        eff, aff = coupling[to_id]
                        coupling[to_id] = (eff, aff + 1)
            return coupling

        curr_map = get_coupling(current_nodes, current_edges)
        parent_map = get_coupling(parent_nodes, parent_edges)

        for mid, (c_eff, c_aff) in curr_map.items():
            p_eff, p_aff = parent_map.get(mid, (0, 0))
            if c_eff != p_eff or c_aff != p_aff:
                # Classify change
                if c_eff > p_eff or c_aff > p_aff:
                    change_type = "increased"
                elif c_eff < p_eff or c_aff < p_aff:
                    change_type = "decreased"
                else:
                    change_type = "stable"
                changes.append(
                    CouplingChange(
                        module_id=mid,
                        previous_efferent=p_eff,
                        current_efferent=c_eff,
                        previous_afferent=p_aff,
                        current_afferent=c_aff,
                        change_type=change_type,
                    )
                )
        return changes

    def _analyze_drift(
        self,
        current_semantics: list[dict[str, Any]],
        parent_semantics: list[dict[str, Any]],
        context_hash: str,
    ) -> list[SemanticDriftItem]:
        drift: list[SemanticDriftItem] = []

        # Check if any decision or assumption was created or updated in this context
        parent_ids = {p["stable_id"] for p in parent_semantics}
        has_decision_change = False

        for curr in current_semantics:
            kind = curr.get("kind")
            stable_id = curr.get("stable_id")

            # Did a decision or assumption change or get added?
            if kind in (SemanticKind.DECISION.value, SemanticKind.ASSUMPTION.value):
                # if not in parent, or summary/confidence/validity changed
                if stable_id not in parent_ids:
                    has_decision_change = True
                    break
                # find parent
                parent_obj = next(
                    (p for p in parent_semantics if p["stable_id"] == stable_id), None
                )
                if parent_obj and (
                    parent_obj["summary"] != curr["summary"]
                    or parent_obj["valid_to_context"] != curr["valid_to_context"]
                ):
                    has_decision_change = True
                    break

        # If decisions/assumptions were NOT updated, check if any module was updated
        if not has_decision_change:
            for curr in current_semantics:
                kind = curr.get("kind")
                if kind in (SemanticKind.MODULE.value, SemanticKind.INTEGRATION.value):
                    stable_id = curr.get("stable_id")
                    # If this module was modified or newly added
                    is_modified = False
                    if stable_id not in parent_ids:
                        is_modified = True
                    else:
                        parent_obj = next(
                            (p for p in parent_semantics if p["stable_id"] == stable_id), None
                        )
                        if parent_obj and parent_obj["summary"] != curr["summary"]:
                            is_modified = True

                    if is_modified:
                        drift.append(
                            SemanticDriftItem(
                                stable_id=stable_id,
                                source_uri=curr.get("source_uri", "unknown"),
                                last_modified=curr.get("created_at", datetime.now(UTC).isoformat()),
                                reason=(
                                    f"Module '{stable_id}' was modified but no corresponding "
                                    "architectural decisions or assumptions were updated in this context."
                                ),
                            )
                        )
        return drift

    def _analyze_domain_erosion(
        self,
        current_nodes: list[dict[str, Any]],
        current_edges: list[dict[str, Any]],
        current_semantics: list[dict[str, Any]],
    ) -> list[DomainErosionItem]:
        erosion: list[DomainErosionItem] = []

        # Build node maps for quick lookup
        node_map = {n["stable_id"]: n for n in current_nodes}

        # Define high-confidence node threshold and low-confidence node threshold
        for edge in current_edges:
            rel = edge.get("relation")
            if rel in (GraphRelation.DEPENDS_ON.value, "depends_on"):
                from_id = edge.get("from_id")
                to_id = edge.get("to_id")

                from_node = node_map.get(from_id)
                to_node = node_map.get(to_id)

                if from_node and to_node:
                    from_conf = float(from_node.get("confidence", 1.0))
                    to_conf = float(to_node.get("confidence", 1.0))

                    # If high-confidence module depends on a low-confidence module
                    if from_conf >= 0.8 and to_conf <= 0.4:
                        severity = from_conf - to_conf
                        erosion.append(
                            DomainErosionItem(
                                stable_id=from_id,
                                severity=severity,
                                description=(
                                    f"High-confidence module '{from_id}' depends on low-confidence "
                                    f"dependency '{to_id}' (confidence: {to_conf}), causing stability erosion."
                                ),
                            )
                        )

        return erosion

    def _analyze_assumption_consequences(
        self,
        current_nodes: list[dict[str, Any]],
        current_edges: list[dict[str, Any]],
        current_semantics: list[dict[str, Any]],
    ) -> list[AssumptionConsequence]:
        consequences: list[AssumptionConsequence] = []

        # Find all assumptions that are invalidated (valid_to_context is not null)
        invalidated_assumptions = [
            s
            for s in current_semantics
            if s.get("kind") == SemanticKind.ASSUMPTION.value
            and s.get("valid_to_context") is not None
        ]

        if not invalidated_assumptions:
            return []

        # Build adjacency maps for the graph
        # We want to find nodes connected to the assumption (or dependent downstream)
        node_deps: dict[str, list[str]] = {}
        for edge in current_edges:
            from_id = edge.get("from_id")
            to_id = edge.get("to_id")
            relation = edge.get("relation")
            if from_id and to_id:
                # Collect references/impact/dependency relations
                node_deps.setdefault(to_id, []).append(from_id)
                node_deps.setdefault(from_id, []).append(to_id)

        for assumption in invalidated_assumptions:
            aid = assumption["stable_id"]
            # Find impacted nodes: start from directly connected and traverse downstream
            visited = {aid}
            queue = [aid]
            impacted_modules: list[str] = []

            while queue:
                curr = queue.pop(0)
                for neighbor in node_deps.get(curr, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        # We only list module/service/package types as impacted code modules
                        # Or if we find they are code elements
                        node = next((n for n in current_nodes if n["stable_id"] == neighbor), None)
                        if node and node.get("node_type") in (
                            GraphNodeType.MODULE.value,
                            GraphNodeType.SERVICE.value,
                            GraphNodeType.PACKAGE.value,
                        ):
                            impacted_modules.append(neighbor)
                        queue.append(neighbor)

            if impacted_modules:
                consequences.append(
                    AssumptionConsequence(
                        assumption_id=aid,
                        impacted_modules=tuple(sorted(impacted_modules)),
                        description=(
                            f"Invalidation of assumption '{aid}' cascades to "
                            f"{len(impacted_modules)} dependent modules: {', '.join(impacted_modules)}."
                        ),
                    )
                )
        return consequences
