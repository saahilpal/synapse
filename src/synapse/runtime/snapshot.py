from __future__ import annotations

from synapse.context.objects import Snapshot
from synapse.replay import ReplayEngine
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


class SnapshotEngine:
    """Creates compact replay checkpoints without making them canonical truth."""

    def __init__(
        self,
        *,
        event_store: SQLiteEventStore,
        object_store: ObjectStore,
        replay_engine: ReplayEngine,
    ) -> None:
        self.event_store = event_store
        self.object_store = object_store
        self.replay_engine = replay_engine

    def create_snapshot(self, *, branch: str) -> Snapshot:
        replay = self.replay_engine.replay()
        context_head = self.event_store.get_active_head(branch)
        snapshot = Snapshot.create(
            context_head=context_head,
            event_sequence=self.event_store.max_event_sequence(),
            state_hash=replay.state_hash,
            object_hashes=tuple(self.event_store.object_hashes()),
        )
        ref = self.object_store.put_snapshot(snapshot)
        self.event_store.record_object_ref(
            object_hash=ref.object_hash,
            kind=ref.kind,
            schema_version=ref.schema_version,
            size_bytes=ref.size_bytes,
            compressed_size_bytes=ref.compressed_size_bytes,
        )
        self.event_store.append_snapshot(snapshot)
        return snapshot
