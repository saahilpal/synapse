from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.context.objects import Confidence, ContextObject, Provenance, SemanticObject
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


class ContextDagError(RuntimeError):
    """Raised when context DAG invariants are violated."""


@dataclass(frozen=True)
class ContextDiff:
    left: str
    right: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]


class ContextDag:
    """Immutable context DAG backed by the object store and SQLite indexes."""

    def __init__(self, *, object_store: ObjectStore, event_store: SQLiteEventStore) -> None:
        self.object_store = object_store
        self.event_store = event_store

    def create_context(
        self,
        *,
        parent_hashes: tuple[str, ...],
        git_commit_hash: str | None,
        branch: str | None,
        event_sequence: int | None,
        semantic_delta: tuple[SemanticObject, ...],
        summary: str,
        provenance: Provenance,
        confidence: Confidence,
        activate: bool = True,
    ) -> ContextObject:
        for parent_hash in parent_hashes:
            if not self.event_store.context_exists(parent_hash):
                raise ContextDagError(f"missing parent context: {parent_hash}")
        context = ContextObject.create(
            parent_hashes=parent_hashes,
            git_commit_hash=git_commit_hash,
            branch=branch,
            event_sequence=event_sequence,
            semantic_delta=semantic_delta,
            summary=summary,
            provenance=provenance,
            confidence=confidence,
        )
        if not context.verify_hash():
            raise ContextDagError(f"context hash verification failed: {context.object_hash}")
        ref = self.object_store.put_context(context)
        self.event_store.record_object_ref(
            object_hash=ref.object_hash,
            kind=ref.kind,
            schema_version=ref.schema_version,
            size_bytes=ref.size_bytes,
            compressed_size_bytes=ref.compressed_size_bytes,
        )
        self.event_store.append_context_object(context)
        if activate:
            self.event_store.set_active_head(
                branch=branch or "detached",
                context_hash=context.object_hash,
            )
        return context

    def get_context(self, context_hash: str) -> ContextObject:
        envelope = self.object_store.get(context_hash)
        if envelope.kind != "context":
            raise ContextDagError(f"object is not a context: {context_hash}")
        context = ContextObject(object_hash=context_hash, **envelope.payload)
        if not context.verify_hash():
            raise ContextDagError(f"context object failed hash verification: {context_hash}")
        return context

    def active_head(self, branch: str) -> str | None:
        return self.event_store.get_active_head(branch)

    def ancestry(self, context_hash: str) -> tuple[str, ...]:
        if not self.event_store.context_exists(context_hash):
            raise ContextDagError(f"unknown context: {context_hash}")
        visited: set[str] = set()
        ordered: list[str] = []
        stack = [context_hash]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            ordered.append(current)
            stack.extend(reversed(self.event_store.parent_hashes(current)))
        return tuple(ordered)

    def is_ancestor(self, *, ancestor_hash: str, descendant_hash: str) -> bool:
        return ancestor_hash in self.ancestry(descendant_hash)

    def divergence(self, left_hash: str, right_hash: str) -> str | None:
        left_ancestry = self.ancestry(left_hash)
        right_ancestry = set(self.ancestry(right_hash))
        for candidate in left_ancestry:
            if candidate in right_ancestry:
                return candidate
        return None

    def rollback(self, *, branch: str, target_hash: str) -> None:
        if not self.event_store.context_exists(target_hash):
            raise ContextDagError(f"unknown rollback target: {target_hash}")
        self.object_store.verify(target_hash)
        self.event_store.set_active_head(branch=branch, context_hash=target_hash)

    def diff(self, left_hash: str, right_hash: str) -> ContextDiff:
        left_ids = {
            str(row["stable_id"])
            for row in self.event_store.semantic_objects_for_context(left_hash)
        }
        right_ids = {
            str(row["stable_id"])
            for row in self.event_store.semantic_objects_for_context(right_hash)
        }
        return ContextDiff(
            left=left_hash,
            right=right_hash,
            added=tuple(sorted(right_ids - left_ids)),
            removed=tuple(sorted(left_ids - right_ids)),
            unchanged=tuple(sorted(left_ids & right_ids)),
        )

    def list_commits(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.event_store.list_context_commits(limit=limit)
