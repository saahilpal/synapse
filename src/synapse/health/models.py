from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from synapse.cognition.objects import SCHEMA_VERSION, FrozenModel


class HealthScore(FrozenModel):
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    schema_version: int = SCHEMA_VERSION


class SubsystemHealth(FrozenModel):
    subsystem_id: str
    afferent_coupling: int
    efferent_coupling: int
    instability: float  # I = Ce / (Ca + Ce)
    change_entropy: float  # Shannon entropy of change frequency
    health_score: float  # Clamped [0.0, 1.0]
    schema_version: int = SCHEMA_VERSION


class ArchitectureHealthReport(FrozenModel):
    context_hash: str
    overall_health: float  # Clamped [0.0, 1.0]
    subsystems: tuple[SubsystemHealth, ...] = ()
    system_entropy: float
    reported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: int = SCHEMA_VERSION
