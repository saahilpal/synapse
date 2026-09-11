from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mcp_serve_stdio_clean_jsonrpc(tmp_path: Path) -> None:
    """Verify synap mcp serve runs in foreground on stdio and emits pure JSON-RPC on stdout."""
    # Initialize a test git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "hello.py").write_text("def hello(): return 'world'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True, capture_output=True
    )

    proc = subprocess.Popen(
        [sys.executable, "-m", "synap_git.cli", "mcp", "serve", str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    init_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }

    try:
        stdout_data, stderr_data = proc.communicate(input=json.dumps(init_msg) + "\n", timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    # Verify stdout contains ONLY valid JSON-RPC response(s)
    lines = [line.strip() for line in stdout_data.splitlines() if line.strip()]
    assert len(lines) >= 1, f"Expected at least one response line on stdout, got: {stdout_data!r}"

    for line in lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Stdout contains non-JSON text: {line!r}") from exc
        assert parsed.get("jsonrpc") == "2.0"

    # Verify first response corresponds to initialize request
    first_response = json.loads(lines[0])
    assert first_response.get("id") == 1
    assert "result" in first_response
    assert "serverInfo" in first_response["result"]
    assert first_response["result"]["serverInfo"]["name"] == "Synap Context Runtime"
