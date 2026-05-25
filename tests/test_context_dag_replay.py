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
from synapse.runtime.replay import ReplayEngine
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


def _semantic(summary: str) -> SemanticObject:
    provenance = Provenance(source_uri="README.md", source_type=SourceType.MARKDOWN)
    return SemanticObject(
        stable_id=SemanticObject.derive_id(
            kind=SemanticKind.ARCHITECTURE,
            source_uri="README.md",
            source_hash="abc",
            content=summary,
        ),
        kind=SemanticKind.ARCHITECTURE,
        summary=summary,
        provenance=provenance,
        confidence=Confidence(score=0.8, rationale="test", evidence_count=1),
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
    )


def test_context_dag_ancestry_diff_and_replay(tmp_path: Path) -> None:
    objects = ObjectStore(tmp_path / "objects")
    store = SQLiteEventStore(tmp_path / "synapse.db")
    objects.initialize()
    store.initialize()
    dag = ContextDag(object_store=objects, event_store=store)
    provenance = Provenance(source_uri="test", source_type=SourceType.SYSTEM)
    confidence = Confidence(score=0.8, rationale="test", evidence_count=1)

    root = dag.create_context(
        parent_hashes=(),
        git_commit_hash=None,
        branch="main",
        event_sequence=None,
        semantic_delta=(_semantic("root architecture"),),
        summary="root",
        provenance=provenance,
        confidence=confidence,
    )
    child = dag.create_context(
        parent_hashes=(root.object_hash,),
        git_commit_hash=None,
        branch="main",
        event_sequence=None,
        semantic_delta=(_semantic("child architecture"),),
        summary="child",
        provenance=provenance,
        confidence=confidence,
    )

    assert dag.ancestry(child.object_hash) == (child.object_hash, root.object_hash)
    assert dag.is_ancestor(ancestor_hash=root.object_hash, descendant_hash=child.object_hash)
    assert dag.diff(root.object_hash, child.object_hash).added
    replay = ReplayEngine(event_store=store, object_store=objects).replay()
    assert replay.context_count == 2
    assert not replay.diagnostics
