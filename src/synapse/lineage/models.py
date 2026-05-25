from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LineageFindingKind(StrEnum):
    MISSING_OBJECT = "missing_object"
    MISSING_PARENT = "missing_parent"
    INVALID_ACTIVE_HEAD = "invalid_active_head"
    CYCLE = "cycle"
    CORRUPT_OBJECT = "corrupt_object"


@dataclass(frozen=True)
class LineageFinding:
    kind: LineageFindingKind
    severity: str
    object_id: str
    summary: str


@dataclass(frozen=True)
class LineageReport:
    ok: bool
    context_count: int
    edge_count: int
    active_head_count: int
    findings: tuple[LineageFinding, ...] = ()
