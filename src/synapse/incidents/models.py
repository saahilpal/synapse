from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    title: str
    context_hash: str | None
    git_commit_hash: str | None
    branch: str | None
    occurred_at: datetime
    assumption_ids: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class IncidentReplay:
    incident: IncidentRecord
    active_assumptions: tuple[str, ...]
    invalidated_assumptions: tuple[str, ...]
    confidence_samples: tuple[dict[str, object], ...]
