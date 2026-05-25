from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from synapse.cognition.objects import GraphEdge, GraphRelation, TrustLevel
from synapse.confidence.models import ConfidenceInputs, ConfidenceScore

TRUST_WEIGHTS: dict[TrustLevel, float] = {
    TrustLevel.UNTRUSTED: 0.05,
    TrustLevel.LOW: 0.3,
    TrustLevel.MEDIUM: 0.6,
    TrustLevel.HIGH: 0.85,
    TrustLevel.VERIFIED: 1.0,
}


class ConfidenceEngine:
    """Deterministic confidence model for confidence(t)."""

    def score(self, inputs: ConfidenceInputs) -> ConfidenceScore:
        freshness_weight = _clamp(inputs.freshness)
        if inputs.created_at is not None and inputs.current_time is not None:
            elapsed_seconds = (inputs.current_time - inputs.created_at).total_seconds()
            half_life_seconds = (inputs.half_life_days or 30.0) * 86400.0
            if half_life_seconds > 0:
                freshness_weight = _clamp(math.pow(0.5, elapsed_seconds / half_life_seconds))

        evidence_weight = 1.0 - math.exp(-max(0, inputs.evidence_count) / 3.0)
        provenance_weight = _clamp(inputs.provenance_trust)
        contradiction_penalty = _clamp(inputs.contradiction_penalty)
        raw = evidence_weight * freshness_weight * provenance_weight
        score = _clamp(raw * (1.0 - contradiction_penalty))
        return ConfidenceScore(
            score=score,
            rationale=(
                "confidence = evidence_weight * freshness_weight * "
                "provenance_weight * (1 - contradiction_penalty)"
            ),
            evidence_weight=evidence_weight,
            freshness_weight=freshness_weight,
            provenance_weight=provenance_weight,
            contradiction_penalty=contradiction_penalty,
        )

    def trust_weight(self, trust_level: TrustLevel) -> float:
        return TRUST_WEIGHTS[trust_level]

    def decay(self, *, current_score: float, half_life_steps: int, elapsed_steps: int) -> float:
        if half_life_steps <= 0:
            return 0.0
        return _clamp(current_score * math.pow(0.5, elapsed_steps / half_life_steps))

    def calculate_time_decay(
        self,
        *,
        created_at: datetime,
        current_time: datetime,
        half_life_days: float = 30.0,
    ) -> float:
        """Calculate time-based decay factor."""
        elapsed = (current_time - created_at).total_seconds()
        half_life_sec = half_life_days * 86400.0
        if half_life_sec <= 0:
            return 0.0
        return _clamp(math.pow(0.5, elapsed / half_life_sec))

    def calculate_contradiction_penalty(
        self,
        stable_id: str,
        edges: Iterable[GraphEdge] | Iterable[dict[str, Any]],
    ) -> float:
        """Calculate contradiction penalty based on contradictions count.

        Uses a smooth, deterministic penalty formula.
        """
        contradict_count = 0
        for edge in edges:
            if isinstance(edge, dict):
                from_id = edge.get("from_id")
                to_id = edge.get("to_id")
                relation = edge.get("relation")
            else:
                from_id = getattr(edge, "from_id", None)
                to_id = getattr(edge, "to_id", None)
                relation = getattr(edge, "relation", None)
                if relation and not isinstance(relation, str):
                    relation = relation.value

            if relation == "contradicts" or relation == GraphRelation.CONTRADICTS.value:
                if from_id == stable_id or to_id == stable_id:
                    contradict_count += 1

        if contradict_count == 0:
            return 0.0
        return _clamp(1.0 - (1.0 / (1.0 + 0.5 * contradict_count)))

    def propagate_provenance_trust(
        self,
        nodes: dict[str, float],
        edges: Iterable[GraphEdge] | Iterable[dict[str, Any]],
        max_depth: int = 10,
    ) -> dict[str, float]:
        """Propagate low-trust ratings from parent/upstream modules downstream.

        If a dependency (to_id) has low trust, propagate the low trust to the
        dependent module (from_id).
        """
        propagated = dict(nodes)

        # Build adjacency list: upstream (to_id) -> downstream (from_id)
        adj: dict[str, list[str]] = {}
        for edge in edges:
            if isinstance(edge, dict):
                from_id = edge.get("from_id")
                to_id = edge.get("to_id")
                relation = edge.get("relation")
            else:
                from_id = getattr(edge, "from_id", None)
                to_id = getattr(edge, "to_id", None)
                relation = getattr(edge, "relation", None)
                if relation and not isinstance(relation, str):
                    relation = relation.value

            if relation == "depends_on" or relation == GraphRelation.DEPENDS_ON.value:
                if from_id and to_id and from_id != to_id:
                    adj.setdefault(to_id, []).append(from_id)

        # Iterative propagation to handle DAG structures up to max_depth
        for _ in range(max_depth):
            changed = False
            for upstream, downstreams in adj.items():
                if upstream not in propagated:
                    continue
                upstream_trust = propagated[upstream]
                if upstream_trust < 0.85:
                    decay_factor = 0.5 + 0.5 * upstream_trust
                    for downstream in downstreams:
                        if downstream in propagated:
                            new_val = _clamp(propagated[downstream] * decay_factor)
                            if new_val < propagated[downstream] - 1e-5:
                                propagated[downstream] = new_val
                                changed = True
            if not changed:
                break

        return propagated


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
