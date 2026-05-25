from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ImpactKind(StrEnum):
    ARCHITECTURE_CHANGE = "architecture_change"
    DEPENDENCY_CHANGE = "dependency_change"
    ASSUMPTION_INVALIDATION = "assumption_invalidation"
    CONFIDENCE_REGRESSION = "confidence_regression"
    DOMAIN_COUPLING = "domain_coupling"


@dataclass(frozen=True)
class ImpactFinding:
    kind: ImpactKind
    severity: str
    headline: str
    stable_id: str | None = None
    confidence_delta: float | None = None


@dataclass(frozen=True)
class SemanticImpactReport:
    left_context: str
    right_context: str
    headline: str
    findings: tuple[ImpactFinding, ...]
