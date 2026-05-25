"""Storage adapters for SQLite and content-addressed object store."""

from synapse.storage.object_store import (
    ObjectCorruptionError,
    ObjectEnvelope,
    ObjectNotFoundError,
    ObjectRef,
    ObjectStore,
)
from synapse.storage.sqlite import SQLiteEventStore, StoreStats

__all__ = [
    "ObjectCorruptionError",
    "ObjectEnvelope",
    "ObjectNotFoundError",
    "ObjectRef",
    "ObjectStore",
    "SQLiteEventStore",
    "StoreStats",
]
