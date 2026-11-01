from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from synap_git.api.app import create_app
from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


@pytest.fixture
def runtime(tmp_path: Path) -> SynapRuntime:
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    r = SynapRuntime(settings)
    r.initialize_storage()

    import json

    (tmp_path / ".synap").mkdir(exist_ok=True, parents=True)
    (tmp_path / ".synap" / "daemon_heartbeat.json").write_text(
        json.dumps({"pid": 1234, "api_token": "test-token"})
    )
    return r


@pytest.fixture
def client(runtime: SynapRuntime) -> TestClient:
    app = create_app(runtime)
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})
    return client


def test_api_get_status(client: TestClient) -> None:
    res = client.get("/api/v1/status")
    assert res.status_code == 200
    data = res.json()
    assert "symbols" in data
    assert "branch" in data


def test_api_get_memory(client: TestClient, runtime: SynapRuntime) -> None:
    with runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO lessons (lesson_id, branch, revert_commit, reverted_from, what_failed, why_failed, files_affected, status, created_at, expires_at)
            VALUES ('L1', 'main', 'h1', 'h0', 'failed', 'reason', '[]', 'approved', 0, 9999999999)
        """
        )

    res = client.get("/api/v1/memory")
    assert res.status_code == 200
    data = res.json()
    assert len(data["approved"]) == 1


def test_api_get_usage(client: TestClient, runtime: SynapRuntime) -> None:
    with runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO llm_calls (call_id, provider, model, input_tokens, output_tokens, cost_usd, purpose, created_at)
            VALUES ('c1', 'anthropic', 'claude', 10, 20, 0.0, 'wiki', 0)
        """
        )

    res = client.get("/api/v1/usage")
    assert res.status_code == 200
    data = res.json()
    assert len(data["calls"]) == 1


def test_api_get_checkpoints(client: TestClient, runtime: SynapRuntime) -> None:
    runtime.store.put_checkpoint("cp1", "main", "hash", "doing something", "[]", "next", "none")

    res = client.get("/api/v1/checkpoints")
    assert res.status_code == 200
    data = res.json()
    assert len(data["checkpoints"]) == 1


def test_api_get_wiki_page(client: TestClient, runtime: SynapRuntime) -> None:
    wiki_dir = runtime.wiki.wiki_dir
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "test-page.md").write_text("wiki content", encoding="utf-8")

    res = client.get("/wiki/test-page.md")
    assert res.status_code == 200
    assert res.json()["content"] == "wiki content"

    res_missing = client.get("/wiki/non-existent")
    assert res_missing.status_code == 200
    assert res_missing.json()["status"] == "error"


def test_status_snapshot_caching(client: TestClient) -> None:
    # First call
    res1 = client.get("/api/v1/status")
    assert res1.status_code == 200
    data1 = res1.json()
    assert "freshness_ttl" in data1
    assert data1["freshness_ttl"] == 2.0
    assert "timestamp" in data1
    assert "cached_at" in data1
    assert "fingerprint" in data1
    assert "is_dirty" in data1

    # Second call immediately after should return cached snapshot
    res2 = client.get("/api/v1/status")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["timestamp"] == data1["timestamp"]
    assert data2["cached_at"] == data1["cached_at"]
    assert data2["fingerprint"] == data1["fingerprint"]

    # Alias /api/status should also share the same cached snapshot
    res3 = client.get("/api/status")
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["timestamp"] == data1["timestamp"]
    assert data3["fingerprint"] == data1["fingerprint"]

    # Invalidate cache and call again
    cache = cast(Any, client.app).state.status_cache
    cache.invalidate()
    res4 = client.get("/api/v1/status")
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["timestamp"] >= data1["timestamp"]


def test_runtime_status_calls_throttled(
    client: TestClient, runtime: SynapRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0
    orig_status = runtime.status

    def mock_status() -> Any:
        nonlocal call_count
        call_count += 1
        return orig_status()

    monkeypatch.setattr(runtime, "status", mock_status)

    cache = cast(Any, client.app).state.status_cache
    cache.invalidate()

    # Make 10 sequential calls across different status aliases
    for _ in range(5):
        r1 = client.get("/api/v1/status")
        assert r1.status_code == 200
        r2 = client.get("/api/status")
        assert r2.status_code == 200

    # Only 1 call to runtime.status should have occurred thanks to the shared snapshot cache
    assert call_count == 1


@pytest.mark.asyncio
async def test_events_sse_stream_initial_and_keepalive(runtime: SynapRuntime) -> None:
    import json
    from unittest.mock import MagicMock

    from fastapi.routing import APIRoute

    app = create_app(runtime)
    mock_request = MagicMock()
    call_count = 0

    async def is_disc() -> bool:
        nonlocal call_count
        call_count += 1
        # Disconnect after emitting initial data and keepalive
        if call_count > 22:
            return True
        return False

    mock_request.is_disconnected = is_disc

    route = next(r for r in app.routes if getattr(r, "path", None) == "/api/v1/events")
    assert isinstance(route, APIRoute)
    response = await route.endpoint(mock_request)
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].startswith("data: ")
    payload = json.loads(chunks[0][len("data: ") :])
    assert "symbols" in payload
    assert "branch" in payload
    assert "fingerprint" in payload
    assert "timestamp" in payload

    # Second event must be a keepalive heartbeat
    assert chunks[1] == ": keepalive\n\n"


@pytest.mark.asyncio
async def test_events_sse_stream_updates_on_fingerprint_change(runtime: SynapRuntime) -> None:
    import json
    from unittest.mock import MagicMock

    from fastapi.routing import APIRoute

    app = create_app(runtime)
    mock_request = MagicMock()
    call_count = 0

    async def is_disc() -> bool:
        nonlocal call_count
        call_count += 1
        if call_count == 10:
            # Simulate a state change by invalidating cache and updating mock
            app.state.status_cache.invalidate()
            orig = app.state.status_cache.get_status

            async def fake_status() -> dict[str, Any]:
                s = await orig()
                s = dict(s)
                s["fingerprint"] = "changed-fingerprint"
                return cast(dict[str, Any], s)

            app.state.status_cache.get_status = fake_status
        if call_count > 25:
            return True
        return False

    mock_request.is_disconnected = is_disc

    route = next(r for r in app.routes if getattr(r, "path", None) == "/api/v1/events")
    assert isinstance(route, APIRoute)
    response = await route.endpoint(mock_request)

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert len(chunks) == 2
    # Both events should be data updates because the fingerprint changed
    assert chunks[0].startswith("data: ")
    assert chunks[1].startswith("data: ")
    p2 = json.loads(chunks[1][len("data: ") :])
    assert p2["fingerprint"] == "changed-fingerprint"
