from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from synapse.cognition.objects import (
    Confidence,
    ContextObject,
    EventRecord,
    EventType,
    GraphEdge,
    GraphNode,
    Provenance,
    SemanticObject,
)


class TransactionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class CognitionCommitRequest:
    operation: str
    event_type: EventType
    source: str
    payload: dict[str, Any]
    actor: str
    git_commit_hash: str | None
    branch: str | None
    parent_hashes: tuple[str, ...]
    semantic_delta: tuple[SemanticObject, ...]
    summary: str
    provenance: Provenance
    confidence: Confidence
    activate: bool = True
    graph_nodes: tuple[GraphNode, ...] = ()
    graph_edges: tuple[GraphEdge, ...] = ()


@dataclass(frozen=True)
class CognitionCommitResult:
    transaction_id: str
    idempotency_key: str
    event: EventRecord
    context: ContextObject
    reused: bool = False


@dataclass(frozen=True)
class TransactionRecoveryFinding:
    transaction_id: str
    status: TransactionStatus
    operation: str
    summary: str
    context_hash: str | None = None
    event_sequence: int | None = None
