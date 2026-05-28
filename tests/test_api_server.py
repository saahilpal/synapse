from __future__ import annotations

from pathlib import Path

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
    return r


@pytest.fixture
def client(runtime: SynapRuntime) -> TestClient:
    app = create_app(runtime)
    return TestClient(app)


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
            INSERT INTO llm_calls (call_id, provider, model, input_tokens, output_tokens, purpose, created_at)
            VALUES ('c1', 'anthropic', 'claude', 10, 20, 'wiki', 0)
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
