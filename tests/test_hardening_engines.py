from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from synapse.assumptions import AssumptionEngine
from synapse.cognition.dag import ContextDag
from synapse.cognition.objects import (
    Confidence,
    EventType,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
)
from synapse.confidence import ConfidenceEngine, ConfidenceInputs
from synapse.evolution import CognitiveEvolutionEngine
from synapse.impact import ImpactKind, SemanticImpactEngine
from synapse.incidents import IncidentEngine
from synapse.lineage import LineageFindingKind, LineageVerifier
from synapse.query import TemporalQueryEngine
from synapse.replay import ReplayEngine
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore
from synapse.temporal import TemporalGraphEngine
from synapse.transactions import CognitionCommitRequest, CognitiveTransactionEngine


def _semantic(kind: SemanticKind, summary: str, source: str = "README.md") -> SemanticObject:
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


def _stores(tmp_path: Path) -> tuple[ObjectStore, SQLiteEventStore, ContextDag]:
    objects = ObjectStore(tmp_path / "objects")
    store = SQLiteEventStore(tmp_path / "synapse.db")
    objects.initialize()
    store.initialize()
    return objects, store, ContextDag(object_store=objects, event_store=store)


def test_cognitive_transaction_is_idempotent(tmp_path: Path) -> None:
    objects, store, _dag = _stores(tmp_path)
    transaction = CognitiveTransactionEngine(event_store=store, object_store=objects)
    semantic = _semantic(SemanticKind.ARCHITECTURE, "Auth trust model uses sessions")
    request = CognitionCommitRequest(
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


def test_lineage_verifier_detects_missing_parent(tmp_path: Path) -> None:
    objects, store, dag = _stores(tmp_path)
    semantic = _semantic(SemanticKind.ARCHITECTURE, "root")
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
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO context_edges(child_hash, parent_hash, edge_type)
            VALUES (?, ?, 'parent')
            """,
            (context.object_hash, "f" * 64),
        )

    report = LineageVerifier(event_store=store, object_store=objects).verify()

    assert not report.ok
    assert report.findings[0].kind is LineageFindingKind.MISSING_PARENT


def test_replay_engine_detects_context_corruption(tmp_path: Path) -> None:
    objects, store, dag = _stores(tmp_path)
    semantic = _semantic(SemanticKind.ARCHITECTURE, "root")
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


def test_impact_temporal_query_and_temporal_graph(tmp_path: Path) -> None:
    objects, store, dag = _stores(tmp_path)
    left_semantic = _semantic(SemanticKind.ARCHITECTURE, "Auth uses sessions")
    right_semantic = _semantic(SemanticKind.ARCHITECTURE, "Auth trust model uses tokens")
    left = dag.create_context(
        parent_hashes=(),
        git_commit_hash="a" * 40,
        branch="main",
        event_sequence=None,
        semantic_delta=(left_semantic,),
        summary="before",
        provenance=left_semantic.provenance,
        confidence=left_semantic.confidence,
    )
    right = dag.create_context(
        parent_hashes=(left.object_hash,),
        git_commit_hash="b" * 40,
        branch="main",
        event_sequence=None,
        semantic_delta=(right_semantic,),
        summary="after",
        provenance=right_semantic.provenance,
        confidence=right_semantic.confidence,
    )
    evolution = CognitiveEvolutionEngine(event_store=store, dag=dag)
    impact = SemanticImpactEngine(evolution=evolution).analyze(
        left_context=left.object_hash,
        right_context=right.object_hash,
    )
    query = TemporalQueryEngine(
        event_store=store,
        evolution=evolution,
        assumptions=AssumptionEngine(event_store=store, evolution=evolution),
    ).evolution_between_dates(datetime(2000, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC))
    graph = TemporalGraphEngine(event_store=store, dag=dag).reconstruct(right.object_hash)

    assert impact.findings[0].kind is ImpactKind.ARCHITECTURE_CHANGE
    assert len(query.rows) == 2
    assert {fact.stable_id for fact in graph.facts} >= {
        left_semantic.stable_id,
        right_semantic.stable_id,
    }


def test_confidence_engine_scores_and_decays() -> None:
    engine = ConfidenceEngine()

    score = engine.score(ConfidenceInputs(evidence_count=3, freshness=0.8, provenance_trust=0.9))

    assert 0.0 < score.score <= 1.0
    assert engine.decay(current_score=0.8, half_life_steps=10, elapsed_steps=10) == 0.4


def test_incident_engine_links_active_assumptions(tmp_path: Path) -> None:
    objects, store, dag = _stores(tmp_path)
    assumption = _semantic(SemanticKind.ASSUMPTION, "Assume Redis persists sessions")
    context = dag.create_context(
        parent_hashes=(),
        git_commit_hash="a" * 40,
        branch="main",
        event_sequence=None,
        semantic_delta=(assumption,),
        summary="assumption",
        provenance=assumption.provenance,
        confidence=assumption.confidence,
    )
    evolution = CognitiveEvolutionEngine(event_store=store, dag=dag)
    assumptions = AssumptionEngine(event_store=store, evolution=evolution)

    incident = IncidentEngine(
        event_store=store,
        evolution=evolution,
        assumptions=assumptions,
    ).record(
        title="Incident 42",
        summary="session loss",
        branch="main",
        git_commit_hash="a" * 40,
        occurred_at=datetime(2026, 5, 24, tzinfo=UTC),
    )

    assert incident.context_hash == context.object_hash
    assert incident.assumption_ids == (assumption.stable_id,)
