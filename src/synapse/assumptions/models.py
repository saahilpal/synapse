from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from synapse.cognition.objects import SCHEMA_VERSION, FrozenModel


class AssumptionStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"


class AssumptionRecord(FrozenModel):
    stable_id: str
    context_hash: str
    status: AssumptionStatus
    summary: str
    source_uri: str
    confidence: float = Field(ge=0.0, le=1.0)
    invalidated_by_context: str | None = None
    invalidation_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
