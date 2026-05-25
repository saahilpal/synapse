from __future__ import annotations

from uuid import uuid4

from synapse.context.dag import ContextDagError
from synapse.context.objects import ContextObject, EventRecord
from synapse.serialization import stable_hash
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore
from synapse.transactions.models import (
    ContextCommitRequest,
    ContextCommitResult,
    TransactionRecoveryFinding,
    TransactionStatus,
)


class ContextTransactionError(RuntimeError):
    """Raised when an atomic context update cannot be completed."""


class ContextTransactionEngine:
    """Journaled transaction boundary for event + object + context writes.

    Filesystem objects cannot participate in SQLite transactions directly, so Synapse
    uses an explicit transaction journal. Recovery can then distinguish committed
    contexts from interrupted writes and verify referenced objects during replay.
    """

    def __init__(self, *, event_store: SQLiteEventStore, object_store: ObjectStore) -> None:
        self.event_store = event_store
        self.object_store = object_store

    def commit_context_update(self, request: ContextCommitRequest) -> ContextCommitResult:
        idempotency_key = self.idempotency_key(request)
        existing = self.event_store.transaction_by_idempotency_key(idempotency_key)
        if existing and existing.get("status") == TransactionStatus.COMMITTED.value:
            return self._committed_result(existing, idempotency_key)

        transaction_id = str(uuid4())
        row = self.event_store.start_transaction(
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
            operation=request.operation,
        )
        transaction_id = str(row["transaction_id"])
        try:
            for parent_hash in request.parent_hashes:
                if not self.event_store.context_exists(parent_hash):
                    raise ContextDagError(f"missing parent context: {parent_hash}")

            payload_ref = self.object_store.put(kind="event_payload", payload=request.payload)
            self.event_store.record_object_ref(
                object_hash=payload_ref.object_hash,
                kind=payload_ref.kind,
                schema_version=payload_ref.schema_version,
                size_bytes=payload_ref.size_bytes,
                compressed_size_bytes=payload_ref.compressed_size_bytes,
            )
            self.event_store.record_transaction_object(
                transaction_id=transaction_id,
                object_hash=payload_ref.object_hash,
                kind=payload_ref.kind,
            )
            event = self.event_store.append_event(
                EventRecord(
                    event_type=request.event_type,
                    source=request.source,
                    payload_hash=payload_ref.object_hash,
                    payload=request.payload,
                    actor=request.actor,
                    git_commit_hash=request.git_commit_hash,
                    branch=request.branch,
                )
            )
            context = ContextObject.create(
                parent_hashes=request.parent_hashes,
                git_commit_hash=request.git_commit_hash,
                branch=request.branch,
                event_sequence=event.sequence,
                semantic_delta=request.semantic_delta,
                graph_nodes=request.graph_nodes,
                graph_edges=request.graph_edges,
                summary=request.summary,
                provenance=request.provenance,
                confidence=request.confidence,
            )
            if not context.verify_hash():
                raise ContextTransactionError(
                    f"context hash verification failed: {context.object_hash}"
                )
            context_ref = self.object_store.put_context(context)
            self.event_store.record_object_ref(
                object_hash=context_ref.object_hash,
                kind=context_ref.kind,
                schema_version=context_ref.schema_version,
                size_bytes=context_ref.size_bytes,
                compressed_size_bytes=context_ref.compressed_size_bytes,
            )
            self.event_store.record_transaction_object(
                transaction_id=transaction_id,
                object_hash=context_ref.object_hash,
                kind=context_ref.kind,
            )
            self.event_store.append_context_object(context)
            if request.activate:
                self.event_store.set_active_head(
                    branch=request.branch or "detached",
                    context_hash=context.object_hash,
                )
            self.event_store.finish_transaction(
                transaction_id=transaction_id,
                status=TransactionStatus.COMMITTED.value,
                event_sequence=event.sequence,
                context_hash=context.object_hash,
            )
            # Invalidate cached projections reactively on updates
            self.event_store.clear_projection_cache()
        except Exception as exc:
            self.event_store.finish_transaction(
                transaction_id=transaction_id,
                status=TransactionStatus.FAILED.value,
                error_message=str(exc),
            )
            raise
        return ContextCommitResult(
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
            event=event,
            context=context,
        )

    def recover(self) -> tuple[TransactionRecoveryFinding, ...]:
        findings: list[TransactionRecoveryFinding] = []
        for row in self.event_store.list_transactions(status=TransactionStatus.IN_PROGRESS.value):
            self.event_store.finish_transaction(
                transaction_id=str(row["transaction_id"]),
                status=TransactionStatus.FAILED.value,
                error_message="transaction was interrupted before commit",
            )
            findings.append(
                TransactionRecoveryFinding(
                    transaction_id=str(row["transaction_id"]),
                    status=TransactionStatus.FAILED,
                    operation=str(row["operation"]),
                    summary="interrupted transaction marked failed for replay-safe recovery",
                    context_hash=row.get("context_hash"),
                    event_sequence=_optional_int(row.get("event_sequence")),
                )
            )
        return tuple(findings)

    def idempotency_key(self, request: ContextCommitRequest) -> str:
        return stable_hash(
            {
                "operation": request.operation,
                "event_type": request.event_type.value,
                "source": request.source,
                "payload": request.payload,
                "actor": request.actor,
                "git_commit_hash": request.git_commit_hash,
                "branch": request.branch,
                "parent_hashes": request.parent_hashes,
                "semantic_ids": tuple(item.stable_id for item in request.semantic_delta),
                "graph_node_ids": tuple(item.stable_id for item in request.graph_nodes),
                "graph_edge_ids": tuple(item.stable_id for item in request.graph_edges),
                "summary": request.summary,
                "activate": request.activate,
            }
        )

    def _committed_result(
        self,
        row: dict[str, object],
        idempotency_key: str,
    ) -> ContextCommitResult:
        event_sequence = _optional_int(row.get("event_sequence"))
        context_hash = row.get("context_hash")
        if event_sequence is None or context_hash is None:
            raise ContextTransactionError("committed transaction is missing commit metadata")
        event = self.event_store.get_event_by_sequence(event_sequence)
        if event is None:
            raise ContextTransactionError(
                f"committed transaction references missing event: {event_sequence}"
            )
        envelope = self.object_store.get(str(context_hash))
        context = ContextObject(object_hash=str(context_hash), **envelope.payload)
        return ContextCommitResult(
            transaction_id=str(row["transaction_id"]),
            idempotency_key=idempotency_key,
            event=event,
            context=context,
            reused=True,
        )


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))
