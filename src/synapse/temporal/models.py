from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from synapse.cognition.objects import SCHEMA_VERSION, Confidence, FrozenModel, Provenance


class EvolutionInterval(FrozenModel):
    """Validity interval for a fact in context/Git lineage time."""

    valid_from_context: str
    valid_to_context: str | None = None
    valid_from_git: str | None = None
    valid_to_git: str | None = None
    created_at: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    @property
    def active(self) -> bool:
        return self.valid_to_context is None and self.valid_to_git is None


class ConfidenceWindow(FrozenModel):
    """Confidence sample for confidence(t)."""

    context_hash: str
    git_commit_hash: str | None = None
    branch: str | None = None
    confidence: Confidence
    observed_at: datetime
    evidence_count: int = Field(ge=0)
    schema_version: int = SCHEMA_VERSION


class ProvenanceLink(FrozenModel):
    """One hop in a provenance chain."""

    context_hash: str
    provenance: Provenance
    relation: str = "observed_in"
    schema_version: int = SCHEMA_VERSION


class TemporalFact(FrozenModel):
    """A cognition fact with validity, confidence, and provenance evolution."""

    stable_id: str
    kind: str
    summary: str
    interval: EvolutionInterval
    confidence_over_time: tuple[ConfidenceWindow, ...] = ()
    provenance_chain: tuple[ProvenanceLink, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
