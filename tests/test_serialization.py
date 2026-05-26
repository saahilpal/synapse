from __future__ import annotations

from datetime import UTC, datetime

from synapse.utils.serialization import pack_canonical, stable_hash


def test_stable_hash_is_order_independent() -> None:
    left = {"b": 2, "a": {"z": 1, "c": 3}}
    right = {"a": {"c": 3, "z": 1}, "b": 2}

    assert stable_hash(left) == stable_hash(right)
    assert pack_canonical(left) == pack_canonical(right)


def test_datetime_serialization_is_canonical() -> None:
    payload = {"created_at": datetime(2026, 5, 24, 12, 0, tzinfo=UTC)}

    assert stable_hash(payload) == stable_hash({"created_at": "2026-05-24T12:00:00+00:00"})
