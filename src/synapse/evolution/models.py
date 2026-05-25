from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from synapse.cognition.objects import SCHEMA_VERSION, FrozenModel


class EvolutionKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    CONFIDENCE_CHANGED = "confidence_changed"
    UNCHANGED = "unchanged"
    INVALIDATED = "invalidated"
    REACTIVATED = "reactivated"


class SemanticDiffItem(FrozenModel):
    stable_id: str
    kind: str
    change: EvolutionKind
    before_summary: str | None = None
    after_summary: str | None = None
    before_confidence: float | None = None
    after_confidence: float | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION


class SemanticDiff(FrozenModel):
    left_context: str
    right_context: str
    headline: str
    added: tuple[SemanticDiffItem, ...] = ()
    removed: tuple[SemanticDiffItem, ...] = ()
    changed: tuple[SemanticDiffItem, ...] = ()
    confidence_changed: tuple[SemanticDiffItem, ...] = ()
    unchanged_count: int = 0
    schema_version: int = SCHEMA_VERSION


class TimelineEvent(FrozenModel):
    context_hash: str
    event_sequence: int | None = None
    git_commit_hash: str | None = None
    branch: str | None = None
    summary: str
    confidence: float
    created_at: datetime
    semantic_counts: dict[str, int] = Field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION


class ConfidenceEvolution(FrozenModel):
    stable_id: str
    samples: tuple[dict[str, Any], ...] = ()
    trend: str
    schema_version: int = SCHEMA_VERSION


class BranchDivergence(FrozenModel):
    left_branch: str
    right_branch: str
    left_head: str | None
    right_head: str | None
    common_context: str | None
    diverged: bool
    schema_version: int = SCHEMA_VERSION


class CognitiveReplayState(FrozenModel):
    context_hash: str | None
    branch: str | None = None
    events: tuple[TimelineEvent, ...] = ()
    active_assumptions: tuple[str, ...] = ()
    invalidated_assumptions: tuple[str, ...] = ()
    confidence_samples: tuple[dict[str, Any], ...] = ()
    schema_version: int = SCHEMA_VERSION


class CouplingChange(FrozenModel):
    module_id: str
    previous_efferent: int
    current_efferent: int
    previous_afferent: int
    current_afferent: int
    change_type: str  # "increased", "decreased", "stable"
    schema_version: int = SCHEMA_VERSION


class SemanticDriftItem(FrozenModel):
    stable_id: str
    source_uri: str
    last_modified: str
    reason: str
    schema_version: int = SCHEMA_VERSION


class DomainErosionItem(FrozenModel):
    stable_id: str
    severity: float  # [0.0, 1.0]
    description: str
    schema_version: int = SCHEMA_VERSION


class AssumptionConsequence(FrozenModel):
    assumption_id: str
    impacted_modules: tuple[str, ...]
    description: str
    schema_version: int = SCHEMA_VERSION


class ReasoningReport(FrozenModel):
    context_hash: str
    coupling_changes: tuple[CouplingChange, ...] = ()
    semantic_drift: tuple[SemanticDriftItem, ...] = ()
    domain_erosion: tuple[DomainErosionItem, ...] = ()
    assumption_consequences: tuple[AssumptionConsequence, ...] = ()
    schema_version: int = SCHEMA_VERSION


class MergeConflictKind(StrEnum):
    MODIFY_MODIFY = "modify_modify"
    ASSUMPTION_CONFLICT = "assumption_conflict"
    REMOVE_MODIFY = "remove_modify"


class CognitiveMergeConflict(FrozenModel):
    stable_id: str
    conflict_type: MergeConflictKind
    left_summary: str | None = None
    right_summary: str | None = None
    description: str
    resolution_candidates: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION


class CognitiveMergeReport(FrozenModel):
    left_context: str
    right_context: str
    common_ancestor: str | None
    conflicts: tuple[CognitiveMergeConflict, ...] = ()
    can_auto_merge: bool
    schema_version: int = SCHEMA_VERSION
