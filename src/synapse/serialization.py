from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import msgpack
from pydantic import BaseModel

CANONICAL_MSGPACK_KWARGS: dict[str, bool] = {
    "use_bin_type": True,
    "strict_types": True,
}


class SerializationError(ValueError):
    """Raised when a value cannot be serialized deterministically."""


def to_primitive(value: Any) -> Any:
    """Convert supported Python values to deterministic msgpack-compatible values."""

    if isinstance(value, BaseModel):
        return to_primitive(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): to_primitive(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, tuple | list):
        return [to_primitive(item) for item in value]
    if isinstance(value, set | frozenset):
        return [to_primitive(item) for item in sorted(value, key=repr)]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return value.as_posix()
    if value is None or isinstance(value, str | int | float | bool | bytes):
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [to_primitive(item) for item in value]
    raise SerializationError(f"Unsupported value for canonical serialization: {type(value)!r}")


def pack_canonical(value: Any) -> bytes:
    """Serialize a value with stable map ordering and no ambient Python object state."""

    primitive = to_primitive(value)
    return cast(bytes, msgpack.packb(primitive, **CANONICAL_MSGPACK_KWARGS))


def unpack_canonical(data: bytes) -> Any:
    return msgpack.unpackb(data, raw=False, strict_map_key=False)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(pack_canonical(value)).hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
