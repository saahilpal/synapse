from __future__ import annotations

from pathlib import Path

import pytest

from synapse.storage.object_store import ObjectCorruptionError, ObjectStore


def test_object_store_put_get_verify(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path / "objects")
    store.initialize()

    ref = store.put(kind="test", payload={"b": 2, "a": 1})
    envelope = store.get(ref.object_hash)

    assert envelope.kind == "test"
    assert envelope.payload == {"a": 1, "b": 2}
    assert store.verify(ref.object_hash).object_hash == ref.object_hash


def test_object_store_detects_corruption(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path / "objects")
    store.initialize()
    ref = store.put(kind="test", payload={"a": 1})

    ref.path.write_bytes(b"corrupted")

    with pytest.raises(ObjectCorruptionError):
        store.verify(ref.object_hash)
