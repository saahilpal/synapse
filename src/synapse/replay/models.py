from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ReplayDiagnosticLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ReplayDiagnostic:
    level: str
    message: str
    object_id: str | None = None


@dataclass(frozen=True)
class ReplayTraceEvent:
    sequence: int | None
    operation: str
    object_id: str | None
    status: str
    detail: dict[str, Any]


@dataclass(frozen=True)
class ReconstructedLineage:
    context_hash: str
    parent_hashes: tuple[str, ...]
    git_commit_hash: str | None
    branch: str | None
    event_sequence: int | None


@dataclass(frozen=True)
class ReplayResult:
    event_count: int
    context_count: int
    state_hash: str
    diagnostics: tuple[ReplayDiagnostic, ...] = ()
    trace: tuple[ReplayTraceEvent, ...] = ()
    lineage: tuple[ReconstructedLineage, ...] = ()
    checkpoint_sequence: int | None = None
