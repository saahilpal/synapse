from __future__ import annotations

from collections import Counter

from synapse.cognition.drift import DriftFinding
from synapse.drift.models import DriftTimeline, DriftTimelinePoint

SEVERITY_WEIGHTS = {"low": 0.25, "medium": 0.6, "high": 0.9, "critical": 1.0}


class DriftTimelineEngine:
    """Scores drift severity and instability over context time."""

    def build(self, findings: tuple[DriftFinding, ...]) -> DriftTimeline:
        by_context: dict[str, list[DriftFinding]] = {}
        for finding in findings:
            context_hash = finding.context_hash or "unknown"
            by_context.setdefault(context_hash, []).append(finding)
        points: list[DriftTimelinePoint] = []
        for context_hash, grouped in sorted(by_context.items()):
            severity_score = sum(SEVERITY_WEIGHTS.get(item.severity, 0.5) for item in grouped)
            kind_counts = Counter(item.kind.value for item in grouped)
            entropy_score = min(1.0, len(kind_counts) / 5.0 + len(grouped) / 20.0)
            points.append(
                DriftTimelinePoint(
                    context_hash=context_hash,
                    finding_count=len(grouped),
                    severity_score=round(severity_score, 4),
                    entropy_score=round(entropy_score, 4),
                )
            )
        instability_score = round(sum(point.entropy_score for point in points), 4)
        return DriftTimeline(
            points=tuple(points),
            instability_score=instability_score,
            findings=findings,
        )
