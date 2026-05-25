from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConfidenceInputs:
    evidence_count: int
    freshness: float
    provenance_trust: float
    contradiction_penalty: float = 0.0
    created_at: datetime | None = None
    current_time: datetime | None = None
    half_life_days: float | None = None


@dataclass(frozen=True)
class ConfidenceScore:
    score: float
    rationale: str
    evidence_weight: float
    freshness_weight: float
    provenance_weight: float
    contradiction_penalty: float
