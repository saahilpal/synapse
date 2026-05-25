from __future__ import annotations

import os
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse.cognition.objects import ContextObject, Snapshot
from synapse.serialization import pack_canonical, stable_hash, unpack_canonical

OBJECT_MAGIC = b"SYNOBJ1\n"
DEFAULT_COMPRESSION_LEVEL = 6


class ObjectStoreError(RuntimeError):
    """Base error for content-addressed object storage."""


class ObjectNotFoundError(ObjectStoreError):
    """Raised when an object hash is not present."""


class ObjectCorruptionError(ObjectStoreError):
    """Raised when an object fails decompression, decoding, or hash verification."""


@dataclass(frozen=True)
class ObjectRef:
    object_hash: str
    kind: str
    schema_version: int
    size_bytes: int
    compressed_size_bytes: int
    path: Path


@dataclass(frozen=True)
class ObjectEnvelope:
    object_hash: str
    kind: str
    schema_version: int
    payload: dict[str, Any]


class ObjectStore:
    """Git-like content-addressed store for immutable Synapse objects."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, *, kind: str, payload: dict[str, Any], schema_version: int = 1) -> ObjectRef:
        envelope = {
            "kind": kind,
            "schema_version": schema_version,
            "payload": payload,
        }
        canonical = pack_canonical(envelope)
        object_hash = stable_hash(envelope)
        path = self.path_for(object_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        compressed = OBJECT_MAGIC + zlib.compress(canonical, level=DEFAULT_COMPRESSION_LEVEL)
        if path.exists():
            self.verify(object_hash)
            return ObjectRef(
                object_hash=object_hash,
                kind=kind,
                schema_version=schema_version,
                size_bytes=len(canonical),
                compressed_size_bytes=path.stat().st_size,
                path=path,
            )
        fd, tmp_name = tempfile.mkstemp(prefix=f".{object_hash}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                tmp_file.write(compressed)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_name, path)
        finally:
            tmp_path = Path(tmp_name)
            if tmp_path.exists():
                tmp_path.unlink()
        return ObjectRef(
            object_hash=object_hash,
            kind=kind,
            schema_version=schema_version,
            size_bytes=len(canonical),
            compressed_size_bytes=len(compressed),
            path=path,
        )

    def put_context(self, context: ContextObject) -> ObjectRef:
        ref = self.put(
            kind="context",
            payload=context.object_payload(),
            schema_version=context.schema_version,
        )
        if ref.object_hash != context.object_hash:
            raise ObjectCorruptionError(
                f"context hash mismatch: model={context.object_hash} store={ref.object_hash}"
            )
        return ref

    def put_snapshot(self, snapshot: Snapshot) -> ObjectRef:
        ref = self.put(
            kind="snapshot",
            payload=snapshot.object_payload(),
            schema_version=snapshot.schema_version,
        )
        if ref.object_hash != snapshot.snapshot_hash:
            raise ObjectCorruptionError(
                f"snapshot hash mismatch: model={snapshot.snapshot_hash} store={ref.object_hash}"
            )
        return ref

    def get(self, object_hash: str) -> ObjectEnvelope:
        path = self.path_for(object_hash)
        if not path.exists():
            raise ObjectNotFoundError(object_hash)
        try:
            data = path.read_bytes()
            if not data.startswith(OBJECT_MAGIC):
                raise ObjectCorruptionError(f"invalid object magic for {object_hash}")
            canonical = zlib.decompress(data[len(OBJECT_MAGIC) :])
            envelope = unpack_canonical(canonical)
        except ObjectStoreError:
            raise
        except Exception as exc:
            raise ObjectCorruptionError(f"cannot read object {object_hash}: {exc}") from exc
        actual_hash = stable_hash(envelope)
        if actual_hash != object_hash:
            raise ObjectCorruptionError(
                f"object hash mismatch for {object_hash}: decoded as {actual_hash}"
            )
        if not isinstance(envelope, dict):
            raise ObjectCorruptionError(f"object envelope is not a map: {object_hash}")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise ObjectCorruptionError(f"object payload is not a map: {object_hash}")
        return ObjectEnvelope(
            object_hash=object_hash,
            kind=str(envelope.get("kind")),
            schema_version=int(envelope.get("schema_version", 0)),
            payload=payload,
        )

    def verify(self, object_hash: str) -> ObjectRef:
        envelope = self.get(object_hash)
        canonical = pack_canonical(
            {
                "kind": envelope.kind,
                "schema_version": envelope.schema_version,
                "payload": envelope.payload,
            }
        )
        path = self.path_for(object_hash)
        return ObjectRef(
            object_hash=object_hash,
            kind=envelope.kind,
            schema_version=envelope.schema_version,
            size_bytes=len(canonical),
            compressed_size_bytes=path.stat().st_size,
            path=path,
        )

    def path_for(self, object_hash: str) -> Path:
        if len(object_hash) < 3:
            raise ValueError("object hash must contain at least three characters")
        return self.root / object_hash[:2] / object_hash[2:]

    def iter_hashes(self) -> list[str]:
        if not self.root.exists():
            return []
        hashes: list[str] = []
        for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
            if len(directory.name) != 2:
                continue
            for path in sorted(child for child in directory.iterdir() if child.is_file()):
                hashes.append(f"{directory.name}{path.name}")
        return hashes
