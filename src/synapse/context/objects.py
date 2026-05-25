from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from synapse.serialization import stable_hash, to_primitive

SCHEMA_VERSION = 2


def utc_now() -> datetime:
    return datetime.now(UTC)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    def canonical(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_primitive(self))


class SourceType(StrEnum):
    CODE = "code"
    MARKDOWN = "markdown"
    GIT = "git"
    MANUAL_NOTE = "manual_note"
    AGENT = "agent"
    SYSTEM = "system"


class TrustLevel(StrEnum):
    UNTRUSTED = "untrusted"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    VERIFIED = "verified"
    STALE = "stale"
    REJECTED = "rejected"


class ValidationState(StrEnum):
    VALIDATED = "validated"
    ASSUMED = "assumed"
    INVALIDATED = "invalidated"


class SemanticKind(StrEnum):
    ARCHITECTURE = "architecture"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"
    TODO = "todo"
    RISK = "risk"
    ROADMAP = "roadmap"
    INTEGRATION = "integration"
    MODULE = "module"
    DEPENDENCY = "dependency"
    NOTE = "note"


class GraphNodeType(StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    PACKAGE = "package"
    DOCUMENT = "document"


class GraphRelation(StrEnum):
    DEPENDS_ON = "depends_on"
    OWNS = "owns"


class EventType(StrEnum):
    REPOSITORY_SCANNED = "repository.scanned"
    FILE_CHANGED = "file.changed"
    GIT_STATE_OBSERVED = "git.state_observed"
    GIT_COMMIT_OBSERVED = "git.commit_observed"
    GIT_CHECKOUT_OBSERVED = "git.checkout_observed"
    GIT_BRANCH_OBSERVED = "git.branch_observed"
    MANUAL_NOTE_ADDED = "manual.note_added"
    CONTEXT_OBJECT_CREATED = "context.object_created"
    CONTEXT_ROLLED_BACK = "context.rolled_back"
    SNAPSHOT_CREATED = "snapshot.created"


class EvidenceSpan(FrozenModel):
    source_uri: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    source_hash: str | None = None
    excerpt_hash: str | None = None


class Provenance(FrozenModel):
    source_uri: str
    source_type: SourceType
    source_hash: str | None = None
    git_commit: str | None = None
    branch: str | None = None
    actor: str = "system"
    extractor: str = "synapse"
    evidence: tuple[EvidenceSpan, ...] = ()


class Confidence(FrozenModel):
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_count: int = Field(ge=0)


class ConfidenceObservation(FrozenModel):
    context_hash: str | None = None
    git_commit_hash: str | None = None
    branch: str | None = None
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_count: int = Field(ge=0)
    observed_at: datetime = Field(default_factory=utc_now)


class Validity(FrozenModel):
    valid_from_context: str | None = None
    valid_to_context: str | None = None
    valid_from_git: str | None = None
    valid_to_git: str | None = None

    @property
    def active(self) -> bool:
        return self.valid_to_context is None and self.valid_to_git is None


class TrustRecord(FrozenModel):
    source: str
    source_type: SourceType
    trust_level: TrustLevel = TrustLevel.MEDIUM
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    rationale: str = "initial classification"
    updated_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION


class SemanticObject(FrozenModel):
    stable_id: str
    kind: SemanticKind
    summary: str
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
    confidence: Confidence
    confidence_history: tuple[ConfidenceObservation, ...] = ()
    validity: Validity = Field(default_factory=Validity)
    created_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION

    @property
    def validation_state(self) -> ValidationState:
        if self.validity.valid_to_context is not None or self.validity.valid_to_git is not None:
            return ValidationState.INVALIDATED
        if self.confidence.score >= 0.85:
            return ValidationState.VALIDATED
        return ValidationState.ASSUMED

    @field_validator("stable_id")
    @classmethod
    def _stable_id_is_not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("stable_id must not be empty")
        return value

    @classmethod
    def derive_id(
        cls,
        *,
        kind: SemanticKind,
        source_uri: str,
        source_hash: str | None,
        heading_path: tuple[str, ...] = (),
        content: str = "",
    ) -> str:
        return stable_hash(
            {
                "kind": kind.value,
                "source_uri": source_uri,
                "source_hash": source_hash,
                "heading_path": heading_path,
                "content_hash": stable_hash({"content": content}),
            }
        )


class GraphNode(FrozenModel):
    stable_id: str
    node_type: GraphNodeType
    labels: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: Confidence
    confidence_history: tuple[ConfidenceObservation, ...] = ()
    provenance: Provenance
    validity: Validity = Field(default_factory=Validity)
    schema_version: int = SCHEMA_VERSION

    @property
    def validation_state(self) -> ValidationState:
        if self.validity.valid_to_context is not None or self.validity.valid_to_git is not None:
            return ValidationState.INVALIDATED
        if self.confidence.score >= 0.85:
            return ValidationState.VALIDATED
        return ValidationState.ASSUMED


class GraphEdge(FrozenModel):
    stable_id: str
    from_id: str
    to_id: str
    relation: GraphRelation
    confidence: Confidence
    confidence_history: tuple[ConfidenceObservation, ...] = ()
    provenance: Provenance
    validity: Validity = Field(default_factory=Validity)
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    @property
    def validation_state(self) -> ValidationState:
        if self.validity.valid_to_context is not None or self.validity.valid_to_git is not None:
            return ValidationState.INVALIDATED
        if self.confidence.score >= 0.85:
            return ValidationState.VALIDATED
        return ValidationState.ASSUMED

    @classmethod
    def derive_id(
        cls,
        *,
        from_id: str,
        to_id: str,
        relation: GraphRelation,
        valid_from_context: str | None = None,
    ) -> str:
        return stable_hash(
            {
                "from_id": from_id,
                "to_id": to_id,
                "relation": relation.value,
                "valid_from_context": valid_from_context,
            }
        )


class EventRecord(FrozenModel):
    event_id: UUID = Field(default_factory=uuid4)
    sequence: int | None = Field(default=None, ge=1)
    event_type: EventType
    source: str
    payload_hash: str
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str = "system"
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    git_commit_hash: str | None = None
    branch: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION

    def with_sequence(self, sequence: int) -> Self:
        return self.model_copy(update={"sequence": sequence})


class ContextObject(FrozenModel):
    object_hash: str
    parent_hashes: tuple[str, ...] = ()
    git_commit_hash: str | None = None
    branch: str | None = None
    event_sequence: int | None = Field(default=None, ge=1)
    semantic_delta: tuple[SemanticObject, ...] = ()
    graph_nodes: tuple[GraphNode, ...] = ()
    graph_edges: tuple[GraphEdge, ...] = ()
    summary: str = ""
    provenance: Provenance
    confidence: Confidence
    created_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        parent_hashes: tuple[str, ...] = (),
        git_commit_hash: str | None,
        branch: str | None,
        event_sequence: int | None,
        semantic_delta: tuple[SemanticObject, ...],
        graph_nodes: tuple[GraphNode, ...] = (),
        graph_edges: tuple[GraphEdge, ...] = (),
        summary: str,
        provenance: Provenance,
        confidence: Confidence,
        created_at: datetime | None = None,
    ) -> Self:
        payload = {
            "parent_hashes": parent_hashes,
            "git_commit_hash": git_commit_hash,
            "branch": branch,
            "event_sequence": event_sequence,
            "semantic_delta": semantic_delta,
            "graph_nodes": graph_nodes,
            "graph_edges": graph_edges,
            "summary": summary,
            "provenance": provenance,
            "confidence": confidence,
            "created_at": created_at or utc_now(),
            "schema_version": SCHEMA_VERSION,
        }
        object_hash = stable_hash(
            {"kind": "context", "schema_version": SCHEMA_VERSION, "payload": payload}
        )
        return cls(object_hash=object_hash, **payload)

    def object_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python", exclude={"object_hash"})
        return cast(dict[str, Any], to_primitive(payload))

    def verify_hash(self) -> bool:
        expected = stable_hash(
            {
                "kind": "context",
                "schema_version": self.schema_version,
                "payload": self.object_payload(),
            }
        )
        return expected == self.object_hash


class Snapshot(FrozenModel):
    snapshot_hash: str
    context_head: str | None
    event_sequence: int
    state_hash: str
    object_hashes: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        context_head: str | None,
        event_sequence: int,
        state_hash: str,
        object_hashes: tuple[str, ...],
        created_at: datetime | None = None,
    ) -> Self:
        payload = {
            "context_head": context_head,
            "event_sequence": event_sequence,
            "state_hash": state_hash,
            "object_hashes": object_hashes,
            "created_at": created_at or utc_now(),
            "schema_version": SCHEMA_VERSION,
        }
        snapshot_hash = stable_hash(
            {"kind": "snapshot", "schema_version": SCHEMA_VERSION, "payload": payload}
        )
        return cls(snapshot_hash=snapshot_hash, **payload)

    def object_payload(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            to_primitive(self.model_dump(mode="python", exclude={"snapshot_hash"})),
        )
