from __future__ import annotations

from dataclasses import dataclass

from synapse.cognition.drift import DriftFinding


@dataclass(frozen=True)
class DriftTimelinePoint:
    context_hash: str
    finding_count: int
    severity_score: float
    entropy_score: float


@dataclass(frozen=True)
class DriftTimeline:
    points: tuple[DriftTimelinePoint, ...]
    instability_score: float
    findings: tuple[DriftFinding, ...]
