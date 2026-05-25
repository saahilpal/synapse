from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from synapse.cognition.dag import ContextDag
from synapse.cognition.objects import (
    Confidence,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
)
from synapse.evolution import CognitiveEvolutionEngine, EvolutionKind
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


def _object(kind: SemanticKind, summary: str, source: str = "README.md") -> SemanticObject:
    provenance = Provenance(source_uri=source, source_type=SourceType.MARKDOWN)
    return SemanticObject(
        stable_id=SemanticObject.derive_id(
            kind=kind,
            source_uri=source,
            source_hash="abc",
            content=summary,
        ),
        kind=kind,
        summary=summary,
        provenance=provenance,
        confidence=Confidence(score=0.8, rationale="test", evidence_count=1),
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
    )


def test_evolution_engine_builds_semantic_diff_and_timeline(tmp_path: Path) -> None:
    objects = ObjectStore(tmp_path / "objects")
    store = SQLiteEventStore(tmp_path / "synapse.db")
    objects.initialize()
    store.initialize()
    dag = ContextDag(object_store=objects, event_store=store)
    provenance = Provenance(source_uri="test", source_type=SourceType.SYSTEM)
    confidence = Confidence(score=0.8, rationale="test", evidence_count=1)

    left = dag.create_context(
        parent_hashes=(),
        git_commit_hash="a" * 40,
        branch="main",
        event_sequence=None,
        semantic_delta=(_object(SemanticKind.ARCHITECTURE, "Auth uses sessions"),),
        summary="before",
        provenance=provenance,
        confidence=confidence,
    )
    right = dag.create_context(
        parent_hashes=(left.object_hash,),
        git_commit_hash="b" * 40,
        branch="main",
        event_sequence=None,
        semantic_delta=(_object(SemanticKind.ARCHITECTURE, "Auth uses token trust model"),),
        summary="after",
        provenance=provenance,
        confidence=confidence,
    )

    engine = CognitiveEvolutionEngine(event_store=store, dag=dag)
    diff = engine.semantic_diff(left.object_hash, right.object_hash)

    assert diff.added[0].change is EvolutionKind.ADDED
    assert diff.removed[0].change is EvolutionKind.REMOVED
    assert "cognition objects" in diff.headline
    assert [event.summary for event in engine.timeline(branch="main")] == ["before", "after"]
