from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from synap_git.api.app import create_app
from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


@pytest.fixture
def web_runtime(tmp_path: Path) -> SynapRuntime:
    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    synap_dir = tmp_path / ".synap"
    synap_dir.mkdir(exist_ok=True, parents=True)
    heartbeat_file = synap_dir / "daemon_heartbeat.json"
    heartbeat_file.write_text(
        json.dumps(
            {
                "pid": 42042,
                "status": "healthy",
                "timestamp": "2026-11-01T12:00:00Z",
                "uptime_seconds": 3600,
                "branch": "main",
                "active_commit": "abcdef123456",
            }
        ),
        encoding="utf-8",
    )
    return runtime


@pytest.fixture
def client(web_runtime: SynapRuntime) -> TestClient:
    app = create_app(web_runtime)
    return TestClient(app)


def test_web_ui_serves_html_and_offline_self_contained(client: TestClient) -> None:
    """Verify index.html is served with status 200 and has zero external CDNs."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    html = res.text

    # Verify zero external CDN links or scripts
    external_scripts = re.findall(r'<script[^>]+src=["\'](https?://[^"\']+)["\']', html)
    external_styles = re.findall(r'<link[^>]+href=["\'](https?://[^"\']+)["\']', html)
    assert external_scripts == [], f"Found external scripts: {external_scripts}"
    assert external_styles == [], f"Found external stylesheets: {external_styles}"

    # Verify CSS variables for modern styling
    assert ':root[data-theme="dark"]' in html
    assert ':root[data-theme="light"]' in html
    assert "--accent:" in html
    assert "--surface:" in html
    assert "--border:" in html


def test_web_ui_semantic_html_and_accessibility(client: TestClient) -> None:
    """Verify semantic HTML tags, roles, and accessibility attributes."""
    html = client.get("/").text

    assert '<header role="banner">' in html
    assert '<main class="grid" role="main">' in html
    assert '<footer role="contentinfo">' in html

    # Modals have dialog role and aria attributes
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="modal-title"' in html
    assert 'aria-labelledby="mcp-modal-title"' in html

    # Search input accessibility
    assert 'type="search"' in html
    assert 'aria-label="Search symbols & context"' in html

    # Toast live region for screen readers
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_web_ui_onboarding_journey_components(client: TestClient) -> None:
    """Verify guided first-run onboarding banner, indexing status, hubs, and quick links."""
    html = client.get("/").text

    # Onboarding banner and title
    assert 'id="onboarding-guide"' in html
    assert 'id="onboarding-title"' in html
    assert "Welcome to Synapse | Developer Onboarding & Health" in html

    # Indexing status: clean / dirty and freshness indicators
    assert 'id="onboarding-tree-status"' in html
    assert 'id="onboarding-freshness"' in html
    assert 'id="onboarding-engine-summary"' in html

    # Architecture overview and top architectural hubs (PageRank)
    assert "3-Layer Engine" in html
    assert "L1 AST Code Graph" in html
    assert "L2 Semantic Wiki" in html
    assert "L3 Behavioral Memory" in html
    assert 'id="onboarding-top-hubs"' in html
    assert "Top Architectural Hubs (PageRank)" in html

    # Quick links
    assert "Search Symbols & Graph" in html
    assert "Inspect Blast Radius" in html
    assert "View Active Rules" in html
    assert "Copy MCP Connection Config" in html
    assert 'id="onboarding-copy-mcp"' in html


def test_web_ui_search_and_modal_ergonomics(client: TestClient) -> None:
    """Verify search shortcut, 250ms debouncing, loading/empty/error states, and table wrapping."""
    html = client.get("/").text

    # Shortcut key reminder
    assert 'class="search-kbd"' in html
    assert "/" in html

    # Search modal structure
    assert 'id="search-modal"' in html
    assert 'id="modal-content"' in html

    # 250ms debounce logic in JavaScript
    assert "setTimeout(() => runSearch(q), 250)" in html

    # Loading, empty, and error states present in JS template
    assert "Searching repository code graph" in html
    assert "No symbols or context found matching" in html
    assert "Search failed:" in html
    assert 'class="spinner"' in html

    # Table layout and word-break wrapping styling to prevent breakage on long paths/symbols
    assert "table-layout: fixed;" in html
    assert "word-break: break-word;" in html
    assert "overflow-wrap: break-word;" in html
    assert "word-break: break-all;" in html


def test_web_ui_keyboard_navigation_and_page_visibility(client: TestClient) -> None:
    """Verify Esc, D, R, / keyboard navigation and Page Visibility API integration."""
    html = client.get("/").text

    # Keyboard navigation handlers
    assert "e.key === '/'" in html
    assert "e.key.toLowerCase() === 'r'" in html
    assert "e.key.toLowerCase() === 'd'" in html
    assert "e.key === 'Escape'" in html
    assert "closeAllModals()" in html

    # Input guard so typing in input doesn't trigger shortcuts
    assert "['INPUT', 'TEXTAREA', 'SELECT'].includes" in html

    # Page Visibility API integration to pause polling on hidden tabs
    assert "if (document.hidden) return;" in html
    assert "document.addEventListener('visibilitychange'" in html


def test_web_ui_mcp_config_snippets_and_copy(client: TestClient) -> None:
    """Verify MCP configuration modal, dynamic repo path substitution, and clipboard helpers."""
    html = client.get("/").text

    assert 'id="mcp-modal"' in html
    assert 'id="claude-mcp-code"' in html
    assert 'id="cursor-mcp-code"' in html
    assert 'id="copy-claude-btn"' in html
    assert 'id="copy-cursor-btn"' in html

    # Verification of MCP serve command generation
    assert '"mcp", "serve"' in html
    assert "claude_desktop_config.json" in html
    assert ".cursor/mcp.json" in html
    assert "navigator.clipboard.writeText" in html


def test_web_ui_api_workflows_status_and_daemon(
    client: TestClient, web_runtime: SynapRuntime
) -> None:
    """Verify /api/v1/status endpoint feeds Web UI state correctly."""
    res = client.get("/api/v1/status")
    assert res.status_code == 200
    data: dict[str, Any] = res.json()

    assert data["branch"] in ("main", "detached")
    assert data["repository_path"] == str(web_runtime.settings.repository_path)
    assert "daemon" in data
    assert data["daemon"]["status"] == "healthy"
    assert data["daemon"]["pid"] == 42042


def test_web_ui_api_workflows_blast_and_clean_tree(client: TestClient) -> None:
    """Verify /api/v1/blast returns clean status when working tree has no uncommitted changes."""
    res = client.get("/api/v1/blast")
    assert res.status_code == 200
    data: dict[str, Any] = res.json()

    assert data["status"] == "ok"
    assert "blast" in data
    assert data["blast"].get("touched_symbols", []) == []


def test_web_ui_api_workflows_hubs_pagerank(client: TestClient, web_runtime: SynapRuntime) -> None:
    """Verify /api/v1/hubs returns PageRank rankings."""
    # Populate a symbol in the database
    with web_runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO files (file_id, path, git_oid, content_hash, language, updated_at)
            VALUES ('f1', 'src/core.py', 'oid1', 'hash1', 'python', '2026-11-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO symbols (symbol_id, file_id, name, kind, start_line, end_line, ast_hash, metadata_json)
            VALUES ('s1', 'f1', 'CoreEngine', 'class', 1, 50, 'asthash', '{}')
            """
        )

    res = client.get("/api/v1/hubs?limit=5")
    assert res.status_code == 200
    data: dict[str, Any] = res.json()
    assert data["status"] == "ok"
    assert isinstance(data.get("hubs"), list)


def test_web_ui_api_workflows_search_and_inspect_symbol(
    client: TestClient, web_runtime: SynapRuntime
) -> None:
    """Verify /api/v1/search and /api/v1/symbol endpoints for modal inspector workflow."""
    sample_file = (
        web_runtime.settings.repository_path / "src" / "synap_git" / "indexer" / "engine.py"
    )
    sample_file.parent.mkdir(parents=True, exist_ok=True)
    sample_file.write_text("class SynapRuntime:\n    pass\n", encoding="utf-8")

    with web_runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO files (file_id, path, git_oid, content_hash, language, updated_at)
            VALUES ('f2', 'src/synap_git/indexer/engine.py', 'oid2', 'hash2', 'python', '2026-11-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO symbols (symbol_id, file_id, name, kind, start_line, end_line, ast_hash, metadata_json)
            VALUES ('s2', 'f2', 'SynapRuntime', 'class', 1, 2, 'asthash2', '{}')
            """
        )

    # Search for SynapRuntime
    search_res = client.get("/api/v1/search?q=SynapRuntime")
    assert search_res.status_code == 200
    search_data: dict[str, Any] = search_res.json()
    assert search_data["status"] == "ok"

    # Inspect symbol
    inspect_res = client.get(
        "/api/v1/symbol?name=SynapRuntime&file_path=src/synap_git/indexer/engine.py"
    )
    assert inspect_res.status_code == 200
    inspect_data: dict[str, Any] = inspect_res.json()
    assert inspect_data["status"] == "ok"
    assert "symbol" in inspect_data
    assert "callers" in inspect_data
    assert "callees" in inspect_data


def test_web_ui_api_workflows_memory_approve_reject(
    client: TestClient, web_runtime: SynapRuntime
) -> None:
    """Verify approving and rejecting L3 memory lessons via UI action endpoints."""
    with web_runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO lessons (lesson_id, branch, revert_commit, reverted_from, what_failed, why_failed, files_affected, status, created_at, expires_at)
            VALUES ('L_TEST_1', 'main', 'rev1', 'from1', 'broken import', 'missing module', '[]', 'pending', 0, 9999999999)
            """
        )

    # Check pending lesson visible
    mem_res = client.get("/api/v1/memory")
    assert mem_res.status_code == 200
    mem_data: dict[str, Any] = mem_res.json()
    assert any(lesson["lesson_id"] == "L_TEST_1" for lesson in mem_data.get("pending", []))

    # Approve lesson via Web UI endpoint
    approve_res = client.post(
        "/api/v1/memory/approve",
        json={"lesson_id": "L_TEST_1", "why_failed": "Approved in UI test"},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "ok"

    # Verify lesson is now approved
    mem_res2 = client.get("/api/v1/memory")
    mem_data2: dict[str, Any] = mem_res2.json()
    assert any(lesson["lesson_id"] == "L_TEST_1" for lesson in mem_data2.get("approved", []))

    # Reject lesson via Web UI endpoint
    reject_res = client.post(
        "/api/v1/memory/reject",
        json={"lesson_id": "L_TEST_1", "why_failed": "Dismissed in UI test"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "ok"
