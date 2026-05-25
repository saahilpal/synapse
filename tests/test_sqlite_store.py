from __future__ import annotations

from pathlib import Path

from synapse.cognition.objects import EventRecord, EventType
from synapse.storage.object_store import ObjectStore
from synapse.storage.sqlite import SQLiteEventStore


def test_sqlite_store_initializes_wal_and_appends_idempotent_events(tmp_path: Path) -> None:
    objects = ObjectStore(tmp_path / "objects")
    objects.initialize()
    store = SQLiteEventStore(tmp_path / "synapse.db")
    store.initialize()

    ref = objects.put(kind="event_payload", payload={"hello": "world"})
    store.record_object_ref(
        object_hash=ref.object_hash,
        kind=ref.kind,
        schema_version=ref.schema_version,
        size_bytes=ref.size_bytes,
        compressed_size_bytes=ref.compressed_size_bytes,
    )
    event = EventRecord(
        event_type=EventType.MANUAL_NOTE_ADDED,
        source="manual://note",
        payload_hash=ref.object_hash,
        payload={"hello": "world"},
    )

    first = store.append_event(event)
    second = store.append_event(event)

    assert first.sequence == second.sequence
    assert store.stats().events == 1
    assert store.health()["journal_mode"] == "wal"
