from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from synapse.context.dag import ContextDag
from synapse.context.objects import (
    Confidence,
    EventType,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
)
from synapse.replay import ReplayEngine
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore
from synapse.transactions import ContextCommitRequest, ContextTransactionEngine


def _semantic(summary: str, source: str = "README.md") -> SemanticObject:
    provenance = Provenance(source_uri=source, source_type=SourceType.MARKDOWN)
    return SemanticObject(
        stable_id=SemanticObject.derive_id(
            kind=SemanticKind.ARCHITECTURE,
            source_uri=source,
            source_hash="abc",
            content=summary,
        ),
        kind=SemanticKind.ARCHITECTURE,
        summary=summary,
        provenance=provenance,
        confidence=Confidence(score=0.8, rationale="test", evidence_count=1),
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
    )


def _stores(tmp_path: Path) -> tuple[ObjectStore, SQLiteEventStore, ContextDag]:
    objects = ObjectStore(tmp_path / "objects")
    store = SQLiteEventStore(tmp_path / "synapse.db")
    objects.initialize()
    store.initialize()
    return objects, store, ContextDag(object_store=objects, event_store=store)


def test_context_transaction_is_idempotent(tmp_path: Path) -> None:
    objects, store, _dag = _stores(tmp_path)
    transaction = ContextTransactionEngine(event_store=store, object_store=objects)
    semantic = _semantic("Auth trust model uses sessions")
    request = ContextCommitRequest(
        operation="test_commit",
        event_type=EventType.MANUAL_NOTE_ADDED,
        source="manual://note",
        payload={"message": "Auth trust model uses sessions"},
        actor="human",
        git_commit_hash=None,
        branch="main",
        parent_hashes=(),
        semantic_delta=(semantic,),
        summary="manual note",
        provenance=semantic.provenance,
        confidence=semantic.confidence,
    )

    first = transaction.commit_context_update(request)
    second = transaction.commit_context_update(request)

    assert first.context.object_hash == second.context.object_hash
    assert second.reused
    assert store.stats().events == 1
    assert store.stats().transactions == 1


def test_replay_engine_detects_context_corruption(tmp_path: Path) -> None:
    objects, store, dag = _stores(tmp_path)
    semantic = _semantic("root")
    context = dag.create_context(
        parent_hashes=(),
        git_commit_hash=None,
        branch="main",
        event_sequence=None,
        semantic_delta=(semantic,),
        summary="root",
        provenance=semantic.provenance,
        confidence=semantic.confidence,
    )
    objects.path_for(context.object_hash).write_bytes(b"corrupted")

    replay = ReplayEngine(event_store=store, object_store=objects).replay()

    assert replay.diagnostics
    assert replay.diagnostics[0].object_id == context.object_hash
