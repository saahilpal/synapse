from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CognitionTier(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass(frozen=True)
class TierPolicy:
    hot_context_window: int = 10
    warm_context_window: int = 100
    cold_confidence_threshold: float = 0.35


@dataclass(frozen=True)
class TierDecision:
    stable_id: str
    tier: CognitionTier
    reason: str


class CognitionTierEngine:
    """Classifies cognition into hot, warm, and cold tiers for bounded operation."""

    def __init__(self, policy: TierPolicy | None = None) -> None:
        self.policy = policy or TierPolicy()

    def classify(
        self,
        *,
        stable_id: str,
        contexts_since_seen: int,
        confidence: float,
        active: bool,
    ) -> TierDecision:
        if active and contexts_since_seen <= self.policy.hot_context_window:
            return TierDecision(stable_id, CognitionTier.HOT, "active in recent context window")
        if confidence < self.policy.cold_confidence_threshold:
            return TierDecision(stable_id, CognitionTier.COLD, "confidence below cold threshold")
        if contexts_since_seen <= self.policy.warm_context_window:
            return TierDecision(stable_id, CognitionTier.WARM, "recent historical cognition")
        return TierDecision(stable_id, CognitionTier.COLD, "outside warm retention window")
