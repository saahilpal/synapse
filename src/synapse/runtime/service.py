from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.config import SynapseSettings
from synapse.context.dag import ContextDag
from synapse.context.extraction import RepositoryContextBuilder
from synapse.context.objects import (
    Confidence,
    EventRecord,
    EventType,
    Provenance,
    SourceType,
)
from synapse.context.overlay import SemanticOverlaySystem
from synapse.context.scanner import RepositoryScan, RepositoryScanner
from synapse.git import GitRepository, GitState
from synapse.observability import get_logger
from synapse.projections.engine import ProjectionEngine
from synapse.provider.factory import get_llm_provider
from synapse.query.retrieval import HybridRetrievalEngine
from synapse.replay import ReplayEngine, ReplayResult
from synapse.runtime.snapshot import SnapshotEngine
from synapse.security import IngestionSanitizer
from synapse.storage import ObjectStore, SQLiteEventStore
from synapse.transactions import ContextCommitRequest, ContextTransactionEngine


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
    """Application service that coordinates source-of-truth stores and core context engines."""

    def __init__(self, settings: SynapseSettings) -> None:
        self.settings = settings
        assert settings.object_path is not None
        assert settings.sqlite_path is not None
        self.object_store = ObjectStore(settings.object_path)
        self.event_store = SQLiteEventStore(settings.sqlite_path)
        self.dag = ContextDag(object_store=self.object_store, event_store=self.event_store)
        self.git = GitRepository(settings.repository_path)
        self.builder = RepositoryContextBuilder()
        self.transaction_engine = ContextTransactionEngine(
            event_store=self.event_store,
            object_store=self.object_store,
        )
        self.replay_engine = ReplayEngine(
            event_store=self.event_store,
            object_store=self.object_store,
        )
        self.llm_provider = get_llm_provider(settings)
        self.retrieval_engine = HybridRetrievalEngine(
            event_store=self.event_store,
            dag=self.dag,
            llm_provider=self.llm_provider,
        )
        self.overlay_system = SemanticOverlaySystem(self.llm_provider)
        self.projection_engine = ProjectionEngine(
            event_store=self.event_store,
            dag=self.dag,
        )
        self.snapshot_engine = SnapshotEngine(
            event_store=self.event_store,
            object_store=self.object_store,
            replay_engine=self.replay_engine,
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

        parent = self.event_store.get_active_head(git_state.effective_branch)
        if parent:
            ordered_ancestry = self.dag.ancestry(parent)
            ancestry = set(ordered_ancestry)

            node_rows = self.event_store.graph_nodes_for_contexts(ordered_ancestry)
            edge_rows = self.event_store.graph_edges_for_contexts(ordered_ancestry)
            sem_rows = self.event_store.semantic_objects_for_contexts(ordered_ancestry)

            active_nodes: dict[str, dict[str, Any]] = {}
            active_semantics: dict[str, dict[str, Any]] = {}
            active_edges: dict[str, dict[str, Any]] = {}

            nodes_by_ctx: dict[str, list[Any]] = {}
            for r in node_rows:
                nodes_by_ctx.setdefault(str(r["context_hash"]), []).append(r)
            edges_by_ctx: dict[str, list[Any]] = {}
            for r in edge_rows:
                edges_by_ctx.setdefault(str(r["context_hash"]), []).append(r)
            sems_by_ctx: dict[str, list[Any]] = {}
            for r in sem_rows:
                sems_by_ctx.setdefault(str(r["context_hash"]), []).append(r)

            for ctx in reversed(ordered_ancestry):
                for r in nodes_by_ctx.get(ctx, []):
                    valid_to = r.get("valid_to_context")
                    if valid_to and str(valid_to) in ancestry:
                        active_nodes.pop(str(r["stable_id"]), None)
                    else:
                        active_nodes[str(r["stable_id"])] = dict(r)

                for r in edges_by_ctx.get(ctx, []):
                    valid_to = r.get("valid_to_context")
                    if valid_to and str(valid_to) in ancestry:
                        active_edges.pop(str(r["stable_id"]), None)
                    else:
                        active_edges[str(r["stable_id"])] = dict(r)

                for r in sems_by_ctx.get(ctx, []):
                    valid_to = r.get("valid_to_context")
                    if valid_to and str(valid_to) in ancestry:
                        active_semantics.pop(str(r["stable_id"]), None)
                    else:
                        active_semantics[str(r["stable_id"])] = dict(r)

            semantic_objects, graph_nodes, graph_edges = self.builder.build_incremental_scan(
                scan=scan,
                git_state=git_state,
                active_nodes=active_nodes,
                active_semantics=active_semantics,
                active_edges=active_edges,
            )
        else:
            semantic_objects, graph_nodes, graph_edges = self.builder.build_from_scan(
                scan=scan, git_state=git_state
            )

        payload = self._scan_payload(scan, git_state, reason)
        result = self.transaction_engine.commit_context_update(
            ContextCommitRequest(
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
            ContextCommitRequest(
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
        diff = self.dag.diff(left_hash, right_hash)
        return {
            "left": diff.left,
            "right": diff.right,
            "added": diff.added,
            "removed": diff.removed,
            "unchanged": diff.unchanged,
        }

    def list_context_commits(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize_storage()
        return self.dag.list_commits(limit=limit)

    def search_context(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        self.initialize_storage()
        return self.event_store.search_semantic_objects(query=query, limit=limit)

    def query_hybrid(
        self,
        query: str,
        *,
        context_hash: str | None = None,
        max_tokens: int = 4000,
    ) -> tuple[str, list[dict[str, Any]]]:
        self.initialize_storage()
        if not context_hash:
            git_state = self.git.state()
            context_hash = self.event_store.get_active_head(git_state.effective_branch)
            if not context_hash:
                raise ValueError("No active context exists to perform hybrid query.")
        return self.retrieval_engine.retrieve(query, context_hash, max_tokens=max_tokens)

    def add_overlay(
        self,
        target_stable_id: str,
        prompt_instruction: str,
        *,
        actor: str = "agent",
    ) -> str:
        self.initialize_storage()
        return self.overlay_system.generate_and_persist_overlay(
            runtime=self,
            target_stable_id=target_stable_id,
            prompt_instruction=prompt_instruction,
            actor=actor,
        )

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
        return {
            "database": health,
            "objects": object_results,
            "replay": {
                "event_count": replay.event_count,
                "context_count": replay.context_count,
                "state_hash": replay.state_hash,
                "diagnostics": [diagnostic.__dict__ for diagnostic in replay.diagnostics],
            },
        }

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
