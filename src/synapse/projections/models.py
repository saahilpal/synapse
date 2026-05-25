from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ProjectionKind(StrEnum):
    OVERVIEW = "overview"
    SUBSYSTEM = "subsystem"
    REPLAY = "replay"
    DRIFT = "drift"
    ASSUMPTION = "assumption"
    INCIDENT = "incident"
    BRANCH = "branch"


class ProjectionNode(BaseModel):
    id: str
    label: str
    kind: str  # e.g. "module", "decision", "assumption", "incident"
    confidence: float = Field(ge=0.0, le=1.0)
    status: str = "active"  # "active", "drifted", "invalidated", "incident"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectionEdge(BaseModel):
    id: str
    from_id: str
    to_id: str
    relation: str
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectionGraph(BaseModel):
    context_hash: str
    kind: ProjectionKind
    nodes: tuple[ProjectionNode, ...] = ()
    edges: tuple[ProjectionEdge, ...] = ()
