from __future__ import annotations

from pathlib import Path

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
