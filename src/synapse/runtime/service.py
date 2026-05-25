from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.assumptions import AssumptionEngine, AssumptionRecord
from synapse.cognition.dag import ContextDag
from synapse.cognition.drift import DriftDetector, DriftFinding
from synapse.cognition.extraction import RepositoryCognitionBuilder
from synapse.cognition.objects import (
    Confidence,
    EventRecord,
    EventType,
    Provenance,
    SourceType,
    utc_now,
)
from synapse.cognition.scanner import RepositoryScan, RepositoryScanner
from synapse.compact import CognitionCompactor
from synapse.config import SynapseSettings
from synapse.evolution import (
    BranchDivergence,
    CognitiveEvolutionEngine,
    CognitiveMergeManager,
    CognitiveMergeReport,
    CognitiveReasoningEngine,
    CognitiveReplayState,
    ConfidenceEvolution,
    ReasoningReport,
    SemanticDiff,
    TimelineEvent,
)
from synapse.git import GitRepository, GitState
from synapse.health import ArchitectureHealthEngine, ArchitectureHealthReport
from synapse.impact import SemanticImpactEngine, SemanticImpactReport
from synapse.incidents import IncidentEngine, IncidentRecord, IncidentReplay
from synapse.lineage import LineageReport, LineageVerifier
from synapse.observability import get_logger
from synapse.query import TemporalQueryEngine, TemporalQueryResult
from synapse.runtime.replay import ReplayEngine, ReplayResult
from synapse.runtime.snapshot import SnapshotEngine
from synapse.security import IngestionSanitizer
from synapse.storage import ObjectStore, SQLiteEventStore
from synapse.temporal import TemporalGraphEngine, TemporalGraphState
from synapse.transactions import CognitionCommitRequest, CognitiveTransactionEngine


@dataclass(frozen=True)
class RuntimeStatus:
    repository_path: str
    branch: str
    git_commit: str | None
    active_context: str | None
    events: int
    context_objects: int
    semantic_objects: int
    mode: str


class SynapseRuntime:
    """Application service that coordinates source-of-truth stores and cognition engines."""

    def __init__(self, settings: SynapseSettings) -> None:
        self.settings = settings
        assert settings.object_path is not None
        assert settings.sqlite_path is not None
        self.object_store = ObjectStore(settings.object_path)
        self.event_store = SQLiteEventStore(settings.sqlite_path)
        self.dag = ContextDag(object_store=self.object_store, event_store=self.event_store)
        self.git = GitRepository(settings.repository_path)
        self.builder = RepositoryCognitionBuilder()
        self.evolution_engine = CognitiveEvolutionEngine(
            event_store=self.event_store,
            dag=self.dag,
        )
        self.assumption_engine = AssumptionEngine(
            event_store=self.event_store,
            evolution=self.evolution_engine,
        )
        self.replay_engine = ReplayEngine(
            event_store=self.event_store,
            object_store=self.object_store,
        )
        self.transaction_engine = CognitiveTransactionEngine(
            event_store=self.event_store,
            object_store=self.object_store,
        )
        self.lineage_verifier = LineageVerifier(
            event_store=self.event_store,
            object_store=self.object_store,
        )
        self.impact_engine = SemanticImpactEngine(evolution=self.evolution_engine)
        self.query_engine = TemporalQueryEngine(
            event_store=self.event_store,
            evolution=self.evolution_engine,
            assumptions=self.assumption_engine,
        )
        self.temporal_graph_engine = TemporalGraphEngine(
            event_store=self.event_store,
            dag=self.dag,
        )
        from synapse.projections.engine import ProjectionEngine

        self.projection_engine = ProjectionEngine(
            event_store=self.event_store,
            dag=self.dag,
            temporal_graph=self.temporal_graph_engine,
        )
        self.incident_engine = IncidentEngine(
            event_store=self.event_store,
            evolution=self.evolution_engine,
            assumptions=self.assumption_engine,
        )
        self.snapshot_engine = SnapshotEngine(
            event_store=self.event_store,
            object_store=self.object_store,
            replay_engine=self.replay_engine,
        )
        self.health_engine = ArchitectureHealthEngine(
            event_store=self.event_store,
            dag=self.dag,
        )
        self.reasoning_engine = CognitiveReasoningEngine(
            event_store=self.event_store,
            dag=self.dag,
        )
        self.merge_manager = CognitiveMergeManager(
            event_store=self.event_store,
            dag=self.dag,
        )
        self.compactor = CognitionCompactor(
            event_store=self.event_store,
        )
        self.sanitizer = IngestionSanitizer()
        self.logger = get_logger("runtime")

    def initialize_storage(self) -> None:
        self.settings.ensure_directories()
        self.object_store.initialize()
        self.event_store.initialize()
        self.transaction_engine.recover()

    def bootstrap(self, *, force: bool = False) -> str:
        self.initialize_storage()
        git_state = self.git.state()
        branch = git_state.effective_branch
        existing_head = self.event_store.get_active_head(branch)
        if existing_head and not force:
            self.logger.info(
                "bootstrap_skipped_existing_context",
                operation="bootstrap",
                object_id=existing_head,
                result="unchanged",
            )
            return existing_head
        context = self.index_repository(reason="bootstrap", git_state=git_state)
        return context

    def index_repository(self, *, reason: str, git_state: GitState | None = None) -> str:
        self.initialize_storage()
        git_state = git_state or self.git.state()
        scanner = RepositoryScanner(
            repository_path=self.settings.repository_path,
            max_file_bytes=self.settings.max_file_bytes,
        )
        scan = scanner.scan()
        semantic_objects, graph_nodes, graph_edges = self.builder.build_from_scan(
            scan=scan, git_state=git_state
        )
        payload = self._scan_payload(scan, git_state, reason)
        parent = self.event_store.get_active_head(git_state.effective_branch)
        result = self.transaction_engine.commit_context_update(
            CognitionCommitRequest(
                operation="index_repository",
                event_type=EventType.REPOSITORY_SCANNED,
                source=self.settings.repository_path.as_posix(),
                payload=payload,
                actor="system",
                git_commit_hash=git_state.head_commit,
                branch=git_state.effective_branch,
                parent_hashes=(parent,) if parent else (),
                semantic_delta=semantic_objects,
                graph_nodes=graph_nodes,
                graph_edges=graph_edges,
                summary=(
                    f"{reason}: indexed {len(scan.files)} files, "
                    f"{len(scan.manifests)} manifests, {len(semantic_objects)} semantic objects"
                ),
                provenance=Provenance(
                    source_uri=self.settings.repository_path.as_posix(),
                    source_type=SourceType.SYSTEM,
                    git_commit=git_state.head_commit,
                    branch=git_state.effective_branch,
                ),
                confidence=Confidence(
                    score=0.84,
                    rationale="deterministic repository scan and bounded semantic extraction",
                    evidence_count=max(1, len(scan.files)),
                ),
            )
        )
        context = result.context
        self.logger.info(
            "repository_indexed",
            operation="index_repository",
            object_id=context.object_hash,
            result="reused" if result.reused else "created",
            semantic_count=len(semantic_objects),
        )
        return context.object_hash

    def add_note(self, message: str, *, actor: str = "human") -> str:
        self.initialize_storage()
        sanitized = self.sanitizer.sanitize_note(message)
        git_state = self.git.state()
        semantic = self.builder.manual_note(
            message=sanitized,
            branch=git_state.effective_branch,
            git_commit_hash=git_state.head_commit,
            actor=actor,
        )
        parent = self.event_store.get_active_head(git_state.effective_branch)
        result = self.transaction_engine.commit_context_update(
            CognitionCommitRequest(
                operation="add_note",
                event_type=EventType.MANUAL_NOTE_ADDED,
                source="manual://note",
                payload={"message": message},
                actor=actor,
                git_commit_hash=git_state.head_commit,
                branch=git_state.effective_branch,
                parent_hashes=(parent,) if parent else (),
                semantic_delta=(semantic,),
                summary=f"manual note: {message[:120]}",
                provenance=semantic.provenance,
                confidence=semantic.confidence,
            )
        )
        return result.context.object_hash

    def append_event(
        self,
        *,
        event_type: EventType,
        source: str,
        payload: dict[str, Any],
        actor: str,
        git_state: GitState | None,
    ) -> EventRecord:
        ref = self.object_store.put(kind="event_payload", payload=payload)
        self.event_store.record_object_ref(
            object_hash=ref.object_hash,
            kind=ref.kind,
            schema_version=ref.schema_version,
            size_bytes=ref.size_bytes,
            compressed_size_bytes=ref.compressed_size_bytes,
        )
        event = EventRecord(
            event_type=event_type,
            source=source,
            payload_hash=ref.object_hash,
            payload=payload,
            actor=actor,
            git_commit_hash=git_state.head_commit if git_state else None,
            branch=git_state.effective_branch if git_state else None,
        )
        return self.event_store.append_event(event)

    def status(self) -> RuntimeStatus:
        self.initialize_storage()
        git_state = self.git.state()
        stats = self.event_store.stats()
        active_context = self.event_store.get_active_head(git_state.effective_branch)
        return RuntimeStatus(
            repository_path=self.settings.repository_path.as_posix(),
            branch=git_state.effective_branch,
            git_commit=git_state.head_commit,
            active_context=active_context,
            events=stats.events,
            context_objects=stats.context_objects,
            semantic_objects=stats.semantic_objects,
            mode=self.settings.mode.value,
        )

    def replay(self) -> ReplayResult:
        self.initialize_storage()
        return self.replay_engine.replay()

    def create_snapshot(self) -> str:
        self.initialize_storage()
        branch = self.git.state().effective_branch
        return self.snapshot_engine.create_snapshot(branch=branch).snapshot_hash

    def rollback(self, target_hash: str) -> None:
        self.initialize_storage()
        git_state = self.git.state()
        self.append_event(
            event_type=EventType.CONTEXT_ROLLED_BACK,
            source="runtime://rollback",
            payload={"target_hash": target_hash, "branch": git_state.effective_branch},
            actor="human",
            git_state=git_state,
        )
        self.dag.rollback(branch=git_state.effective_branch, target_hash=target_hash)

    def diff(self, left_hash: str, right_hash: str) -> dict[str, Any]:
        semantic = self.semantic_diff(left_hash, right_hash)
        return semantic.model_dump(mode="json")

    def dag_diff(self, left_hash: str, right_hash: str) -> dict[str, Any]:
        diff = self.dag.diff(left_hash, right_hash)
        return {
            "left": diff.left,
            "right": diff.right,
            "added": diff.added,
            "removed": diff.removed,
            "unchanged": diff.unchanged,
        }

    def semantic_diff(self, left_hash: str, right_hash: str) -> SemanticDiff:
        self.initialize_storage()
        return self.evolution_engine.semantic_diff(left_hash, right_hash)

    def semantic_impact(self, left_hash: str, right_hash: str) -> SemanticImpactReport:
        self.initialize_storage()
        return self.impact_engine.analyze(left_context=left_hash, right_context=right_hash)

    def timeline(self, *, branch: str | None = None, limit: int = 100) -> tuple[TimelineEvent, ...]:
        self.initialize_storage()
        return self.evolution_engine.timeline(branch=branch, limit=limit)

    def branch_divergence(self, *, left_branch: str, right_branch: str) -> BranchDivergence:
        self.initialize_storage()
        return self.evolution_engine.branch_divergence(
            left_branch=left_branch,
            right_branch=right_branch,
        )

    def confidence_evolution(self, stable_id: str) -> ConfidenceEvolution:
        self.initialize_storage()
        return self.evolution_engine.confidence_evolution(stable_id)

    def replay_cognition(
        self,
        *,
        context_hash: str | None = None,
        branch: str | None = None,
    ) -> CognitiveReplayState:
        self.initialize_storage()
        return self.evolution_engine.replay_cognition(context_hash=context_hash, branch=branch)

    def temporal_graph(self, context_hash: str) -> TemporalGraphState:
        self.initialize_storage()
        return self.temporal_graph_engine.reconstruct(context_hash)

    def lineage(self) -> LineageReport:
        self.initialize_storage()
        return self.lineage_verifier.verify()

    def query_confidence_decay(self, stable_id: str) -> TemporalQueryResult:
        self.initialize_storage()
        return self.query_engine.confidence_decay_for(stable_id)

    def record_incident(
        self,
        *,
        title: str,
        summary: str,
    ) -> IncidentRecord:
        self.initialize_storage()
        git_state = self.git.state()
        return self.incident_engine.record(
            title=title,
            summary=summary,
            branch=git_state.effective_branch,
            git_commit_hash=git_state.head_commit,
            occurred_at=utc_now(),
        )

    def replay_incident(self, incident: IncidentRecord) -> IncidentReplay:
        self.initialize_storage()
        return self.incident_engine.replay(incident)

    def assumptions(self, *, context_hash: str | None = None) -> tuple[AssumptionRecord, ...]:
        self.initialize_storage()
        return self.assumption_engine.list_assumptions(context_hash=context_hash)

    def invalidated_assumptions(
        self,
        *,
        left_hash: str,
        right_hash: str,
        apply: bool = False,
    ) -> tuple[AssumptionRecord, ...]:
        self.initialize_storage()
        return self.assumption_engine.invalidated_between(
            left_context=left_hash,
            right_context=right_hash,
            apply=apply,
        )

    def list_context_commits(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize_storage()
        return self.dag.list_commits(limit=limit)

    def search_cognition(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        self.initialize_storage()
        return self.event_store.search_semantic_objects(query=query, limit=limit)

    def search_memory(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.search_cognition(query, limit=limit)

    def drift(self) -> tuple[DriftFinding, ...]:
        self.initialize_storage()
        git_state = self.git.state()
        scanner = RepositoryScanner(
            repository_path=self.settings.repository_path,
            max_file_bytes=self.settings.max_file_bytes,
        )
        scan = scanner.scan()
        context_hash = self.event_store.get_active_head(git_state.effective_branch)
        return DriftDetector(
            event_store=self.event_store,
            repository_path=self.settings.repository_path,
        ).detect(scan=scan, context_hash=context_hash)

    def doctor(self) -> dict[str, Any]:
        self.initialize_storage()
        health = self.event_store.health()
        object_results: list[dict[str, Any]] = []
        for object_hash in self.event_store.object_hashes():
            try:
                ref = self.object_store.verify(object_hash)
            except Exception as exc:
                object_results.append(
                    {"object_hash": object_hash, "status": "error", "error": str(exc)}
                )
            else:
                object_results.append(
                    {
                        "object_hash": object_hash,
                        "kind": ref.kind,
                        "status": "ok",
                        "size_bytes": ref.size_bytes,
                    }
                )
        replay = self.replay()
        lineage = self.lineage()
        return {
            "database": health,
            "objects": object_results,
            "replay": {
                "event_count": replay.event_count,
                "context_count": replay.context_count,
                "state_hash": replay.state_hash,
                "diagnostics": [diagnostic.__dict__ for diagnostic in replay.diagnostics],
            },
            "lineage": {
                "ok": lineage.ok,
                "context_count": lineage.context_count,
                "edge_count": lineage.edge_count,
                "active_head_count": lineage.active_head_count,
                "findings": [finding.__dict__ for finding in lineage.findings],
            },
        }

    def analyze_health(self, context_hash: str | None = None) -> ArchitectureHealthReport:
        self.initialize_storage()
        if not context_hash:
            git_state = self.git.state()
            context_hash = self.event_store.get_active_head(git_state.effective_branch)
            if not context_hash:
                commits = self.event_store.list_context_commits(limit=1)
                if commits:
                    context_hash = commits[0]["context_hash"]
                else:
                    raise ValueError("No context commits exist to analyze health.")
        return self.health_engine.analyze_health(context_hash)

    def analyze_reasoning(self, context_hash: str | None = None) -> ReasoningReport:
        self.initialize_storage()
        if not context_hash:
            git_state = self.git.state()
            context_hash = self.event_store.get_active_head(git_state.effective_branch)
            if not context_hash:
                commits = self.event_store.list_context_commits(limit=1)
                if commits:
                    context_hash = commits[0]["context_hash"]
                else:
                    raise ValueError("No context commits exist to analyze reasoning.")
        return self.reasoning_engine.analyze_reasoning(context_hash)

    def detect_conflicts(
        self, left_branch_or_hash: str, right_branch_or_hash: str
    ) -> CognitiveMergeReport:
        self.initialize_storage()
        left_hash = self.event_store.get_active_head(left_branch_or_hash) or left_branch_or_hash
        right_hash = self.event_store.get_active_head(right_branch_or_hash) or right_branch_or_hash
        return self.merge_manager.detect_conflicts(left_hash, right_hash)

    def compact(self) -> dict[str, Any]:
        self.initialize_storage()
        return self.compactor.compact()

    def _scan_payload(
        self,
        scan: RepositoryScan,
        git_state: GitState,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "reason": reason,
            "repository_path": scan.repository_path.as_posix(),
            "file_count": len(scan.files),
            "manifest_count": len(scan.manifests),
            "language_counts": scan.language_counts,
            "folder_counts": scan.folder_counts,
            "dependencies": scan.dependencies,
            "git": {
                "is_repository": git_state.is_repository,
                "head_commit": git_state.head_commit,
                "branch": git_state.branch,
                "is_dirty": git_state.is_dirty,
                "is_detached": git_state.is_detached,
                "merge_in_progress": git_state.merge_in_progress,
                "rebase_in_progress": git_state.rebase_in_progress,
            },
        }
