from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TemporalQueryKind(StrEnum):
    COGNITION_BEFORE_COMMIT = "cognition_before_commit"
    EVOLUTION_BETWEEN_DATES = "evolution_between_dates"
    INVALIDATED_ASSUMPTIONS_AFTER = "invalidated_assumptions_after"
    CONFIDENCE_DECAY_FOR = "confidence_decay_for"
    FLEXIBLE_SEARCH = "flexible_search"


@dataclass(frozen=True)
class TemporalQueryResult:
    query: TemporalQueryKind
    rows: tuple[dict[str, Any], ...]
    context_hash: str | None = None
    summary: str = ""
