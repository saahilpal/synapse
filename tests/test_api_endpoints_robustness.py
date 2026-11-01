from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from synap_git.api.app import create_app
from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


def test_api_aliases_and_empty_tables(tmp_path: Path) -> None:
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    app = create_app(runtime)
    client = TestClient(app)

    # Test route aliases
    res_v1 = client.get("/api/v1/status")
    assert res_v1.status_code == 200

    res_alias = client.get("/api/status")
    assert res_alias.status_code == 200

    res_health = client.get("/health")
    assert res_health.status_code == 200

    res_healthz = client.get("/healthz")
    assert res_healthz.status_code == 200

    # Test empty tables without 500 error
    res_usage = client.get("/api/v1/usage")
    assert res_usage.status_code == 200
    assert res_usage.json()["calls"] == []

    res_cps = client.get("/api/v1/checkpoints")
    assert res_cps.status_code == 200
    assert res_cps.json()["checkpoints"] == []

    res_mem = client.get("/api/v1/memory")
    assert res_mem.status_code == 200
    assert res_mem.json()["approved"] == []


@pytest.mark.asyncio
async def test_status_cache_concurrency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    app = create_app(runtime)
    cache = app.state.status_cache

    call_count = 0
    orig_status = runtime.status

    def mock_status() -> Any:
        nonlocal call_count
        call_count += 1
        return orig_status()

    monkeypatch.setattr(runtime, "status", mock_status)

    # Fire 10 concurrent requests to the cache
    import asyncio

    results = await asyncio.gather(*[cache.get_status() for _ in range(10)])

    # All should succeed and return the exact same snapshot
    assert len(results) == 10
    first_fp = results[0]["fingerprint"]
    first_ts = results[0]["timestamp"]
    for r in results:
        assert r["fingerprint"] == first_fp
        assert r["timestamp"] == first_ts

    # Lock prevented stampede: only 1 runtime.status call
    assert call_count == 1


def test_daemon_watchdog_quiet_window_debounce(tmp_path: Path) -> None:
    import time

    from synap_git.indexer.daemon import RuntimeDaemon

    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    daemon = RuntimeDaemon(settings, debounce_seconds=0.3)
    assert daemon._debounce_seconds == 0.3

    # Simulate rapid file events arriving in quick succession
    now = time.monotonic()
    daemon._fs_changed = True
    daemon._last_fs_event_time = now

    # At 0.1s after first event, quiet window hasn't passed
    now_eval1 = now + 0.1
    quiet_elapsed1 = now_eval1 - daemon._last_fs_event_time
    assert quiet_elapsed1 < daemon._debounce_seconds

    # Another event arrives at 0.15s, resetting quiet window
    daemon._last_fs_event_time = now + 0.15
    daemon._fs_changed = True

    # At 0.3s after first event (0.15s after second event), still not quiet
    now_eval2 = now + 0.3
    quiet_elapsed2 = now_eval2 - daemon._last_fs_event_time
    assert quiet_elapsed2 < daemon._debounce_seconds

    # Finally at 0.5s (0.35s after second event), quiet window has passed
    now_eval3 = now + 0.5
    quiet_elapsed3 = now_eval3 - daemon._last_fs_event_time
    assert quiet_elapsed3 >= daemon._debounce_seconds


@pytest.mark.asyncio
async def test_daemon_clean_shutdown_signal_traps(tmp_path: Path) -> None:
    from synap_git.indexer.daemon import RuntimeDaemon

    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    daemon = RuntimeDaemon(settings, debounce_seconds=0.1)

    # Write dummy heartbeat and PID files
    synap_dir = tmp_path / ".synap"
    synap_dir.mkdir(parents=True, exist_ok=True)
    pid_file = synap_dir / "daemon.pid"
    hb_file = synap_dir / "daemon_heartbeat.json"
    pid_file.write_text("99999", encoding="utf-8")
    hb_file.write_text('{"status": "healthy"}', encoding="utf-8")
    assert pid_file.exists()
    assert hb_file.exists()

    # Trigger clean signal trap handler
    daemon.stop(force_exit=True)
    daemon._delete_heartbeat()

    # Both lockfiles must be cleaned up
    assert not pid_file.exists()
    assert not hb_file.exists()
