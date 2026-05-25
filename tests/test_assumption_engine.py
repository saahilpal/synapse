from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from synapse.assumptions import AssumptionEngine, AssumptionStatus
from synapse.cognition.dag import ContextDag
from synapse.cognition.objects import (
    Confidence,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
)
from synapse.evolution import CognitiveEvolutionEngine
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


def _semantic(kind: SemanticKind, summary: str) -> SemanticObject:
    provenance = Provenance(source_uri="README.md", source_type=SourceType.MARKDOWN)
    return SemanticObject(
        stable_id=SemanticObject.derive_id(
            kind=kind,
            source_uri="README.md",
            source_hash="abc",
            content=summary,
        ),
        kind=kind,
        summary=summary,
        provenance=provenance,
        confidence=Confidence(score=0.8, rationale="test", evidence_count=1),
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
    )


def test_assumption_engine_detects_dependency_invalidation(tmp_path: Path) -> None:
    objects = ObjectStore(tmp_path / "objects")
    store = SQLiteEventStore(tmp_path / "synapse.db")
    objects.initialize()
    store.initialize()
    dag = ContextDag(object_store=objects, event_store=store)
    provenance = Provenance(source_uri="test", source_type=SourceType.SYSTEM)
    confidence = Confidence(score=0.8, rationale="test", evidence_count=1)

    left = dag.create_context(
        parent_hashes=(),
        git_commit_hash=None,
        branch="main",
        event_sequence=None,
        semantic_delta=(
            _semantic(SemanticKind.ASSUMPTION, "Payment service assumes Redis persistence"),
            _semantic(SemanticKind.DEPENDENCY, "Dependencies include redis"),
        ),
        summary="before redis removal",
        provenance=provenance,
        confidence=confidence,
    )
    right = dag.create_context(
        parent_hashes=(left.object_hash,),
        git_commit_hash=None,
        branch="main",
        event_sequence=None,
        semantic_delta=(_semantic(SemanticKind.DEPENDENCY, "Dependencies include sqlite"),),
        summary="after redis removal",
        provenance=provenance,
        confidence=confidence,
    )

    evolution = CognitiveEvolutionEngine(event_store=store, dag=dag)
    assumptions = AssumptionEngine(event_store=store, evolution=evolution).invalidated_between(
        left_context=left.object_hash,
        right_context=right.object_hash,
    )

    assert assumptions[0].status is AssumptionStatus.INVALIDATED
    assert "redis" in str(assumptions[0].invalidation_reason).lower()
