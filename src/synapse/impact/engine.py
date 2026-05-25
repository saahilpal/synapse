from __future__ import annotations

from synapse.cognition.objects import SemanticKind
from synapse.evolution import CognitiveEvolutionEngine, EvolutionKind, SemanticDiffItem
from synapse.impact.models import ImpactFinding, ImpactKind, SemanticImpactReport


class SemanticImpactEngine:
    """Converts semantic diffs into architecture-impact findings."""

    def __init__(self, *, evolution: CognitiveEvolutionEngine) -> None:
        self.evolution = evolution

    def analyze(self, *, left_context: str, right_context: str) -> SemanticImpactReport:
        diff = self.evolution.semantic_diff(left_context, right_context)
        findings: list[ImpactFinding] = []
        for item in (*diff.added, *diff.removed, *diff.changed, *diff.confidence_changed):
            finding = self._finding(item)
            if finding is not None:
                findings.append(finding)
        headline = _report_headline(findings)
        return SemanticImpactReport(
            left_context=left_context,
            right_context=right_context,
            headline=headline,
            findings=tuple(findings),
        )

    def _finding(self, item: SemanticDiffItem) -> ImpactFinding | None:
        if item.kind == SemanticKind.ARCHITECTURE.value:
            return ImpactFinding(
                kind=ImpactKind.ARCHITECTURE_CHANGE,
                severity="high" if item.change is EvolutionKind.CHANGED else "medium",
                headline=_architecture_headline(item),
                stable_id=item.stable_id,
            )
        if item.kind == SemanticKind.DEPENDENCY.value:
            return ImpactFinding(
                kind=ImpactKind.DEPENDENCY_CHANGE,
                severity="medium",
                headline=_dependency_headline(item),
                stable_id=item.stable_id,
            )
        if item.kind == SemanticKind.ASSUMPTION.value and item.change is EvolutionKind.REMOVED:
            return ImpactFinding(
                kind=ImpactKind.ASSUMPTION_INVALIDATION,
                severity="high",
                headline="Architectural assumption no longer appears active",
                stable_id=item.stable_id,
            )
        if item.change is EvolutionKind.CONFIDENCE_CHANGED:
            before = item.before_confidence or 0.0
            after = item.after_confidence or 0.0
            if after < before:
                return ImpactFinding(
                    kind=ImpactKind.CONFIDENCE_REGRESSION,
                    severity="medium" if before - after < 0.2 else "high",
                    headline="Confidence in a cognition object declined",
                    stable_id=item.stable_id,
                    confidence_delta=after - before,
                )
        return None


def _architecture_headline(item: SemanticDiffItem) -> str:
    text = (item.after_summary or item.before_summary or "").lower()
    if "trust" in text and "auth" in text:
        return "Authentication trust model changed"
    if "boundary" in text or "coupling" in text:
        return "Service boundary or coupling changed"
    return "Architectural cognition changed"


def _dependency_headline(item: SemanticDiffItem) -> str:
    if item.change is EvolutionKind.REMOVED:
        return "Dependency cognition was removed"
    if item.change is EvolutionKind.ADDED:
        return "Dependency cognition was added"
    return "Dependency cognition changed"


def _report_headline(findings: list[ImpactFinding]) -> str:
    if not findings:
        return "No semantic impact detected"
    high = sum(1 for finding in findings if finding.severity == "high")
    medium = sum(1 for finding in findings if finding.severity == "medium")
    return f"{high} high-impact and {medium} medium-impact cognition changes"
