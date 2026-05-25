from __future__ import annotations

import math
from collections import Counter

from synapse.cognition.dag import ContextDag
from synapse.cognition.objects import GraphNodeType, GraphRelation
from synapse.health.models import ArchitectureHealthReport, SubsystemHealth
from synapse.storage.sqlite import SQLiteEventStore


class ArchitectureHealthEngine:
    """Calculates metrics and compiles architecture health reports."""

    def __init__(self, *, event_store: SQLiteEventStore, dag: ContextDag) -> None:
        self.event_store = event_store
        self.dag = dag

    def analyze_health(self, context_hash: str) -> ArchitectureHealthReport:
        """Evaluate coupling, churn, entropy, and compile a health report."""
        nodes = self.event_store.graph_nodes_for_context(context_hash)
        edges = self.event_store.graph_edges_for_context(context_hash)

        # 1. Identify subsystems (modules, services, packages)
        subsystem_nodes = [
            n
            for n in nodes
            if n["node_type"]
            in (
                GraphNodeType.MODULE.value,
                GraphNodeType.SERVICE.value,
                GraphNodeType.PACKAGE.value,
            )
        ]

        if not subsystem_nodes:
            return ArchitectureHealthReport(
                context_hash=context_hash,
                overall_health=1.0,
                subsystems=(),
                system_entropy=0.0,
            )

        # 2. Compute historical change frequencies for Shannon change entropy
        ancestry_hashes = self.dag.ancestry(context_hash)
        # Fetch all semantic objects across ancestry
        historical_semantics = self.event_store.semantic_objects_for_contexts(ancestry_hashes)

        # Count modifications per subsystem
        change_counts: Counter[str] = Counter()
        subsystem_ids = {n["stable_id"] for n in subsystem_nodes}

        for sem in historical_semantics:
            sid = sem.get("stable_id")
            if isinstance(sid, str) and sid in subsystem_ids:
                change_counts[sid] += 1

        total_changes = sum(change_counts.values())

        # 3. Calculate system-wide Shannon entropy
        system_entropy = 0.0
        if total_changes > 0:
            for sid, count in change_counts.items():
                p = count / total_changes
                system_entropy -= p * math.log2(p)

        # 4. Calculate Subsystem coupling and instability
        subsystems_health: list[SubsystemHealth] = []

        for n in subsystem_nodes:
            sid = n["stable_id"]

            # Afferent coupling (Ca): incoming depends_on
            ca = sum(
                1
                for e in edges
                if e.get("to_id") == sid
                and e.get("relation") in (GraphRelation.DEPENDS_ON.value, "depends_on")
            )
            # Efferent coupling (Ce): outgoing depends_on
            ce = sum(
                1
                for e in edges
                if e.get("from_id") == sid
                and e.get("relation") in (GraphRelation.DEPENDS_ON.value, "depends_on")
            )

            # Instability: Ce / (Ca + Ce)
            instability = ce / (ca + ce) if (ca + ce) > 0 else 0.0

            # Subsystem contribution to change entropy
            subsystem_p = change_counts[sid] / total_changes if total_changes > 0 else 0.0
            subsystem_entropy = -subsystem_p * math.log2(subsystem_p) if subsystem_p > 0.0 else 0.0

            # Calculate individual subsystem health score
            confidence = float(n.get("confidence", 1.0))
            # Heuristic: base health on confidence, penalize instability/coupling and churn (entropy)
            churn_penalty = min(0.4, subsystem_p * 2.0)  # max 40% penalty for massive churn
            instability_penalty = 0.1 * instability
            health_score = max(
                0.0, min(1.0, confidence * (1.0 - instability_penalty) * (1.0 - churn_penalty))
            )

            subsystems_health.append(
                SubsystemHealth(
                    subsystem_id=sid,
                    afferent_coupling=ca,
                    efferent_coupling=ce,
                    instability=instability,
                    change_entropy=subsystem_entropy,
                    health_score=health_score,
                )
            )

        # 5. Calculate overall architecture health index
        overall_health = sum(s.health_score for s in subsystems_health) / len(subsystems_health)

        return ArchitectureHealthReport(
            context_hash=context_hash,
            overall_health=max(0.0, min(1.0, overall_health)),
            subsystems=tuple(subsystems_health),
            system_entropy=system_entropy,
        )
