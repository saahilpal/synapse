from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse.cognition.objects import EventType
from synapse.config import RuntimeProfile, SynapseSettings
from synapse.projections.models import ProjectionKind
from synapse.runtime.service import SynapseRuntime
from synapse.security.redaction import SecretRedactor
from synapse.security.sanitization import SafeMarkdownRenderer
from synapse.security.validation import InputValidator


def test_secret_redaction() -> None:
    redactor = SecretRedactor()

    # Check sensitive key redaction
    assert redactor.redact({"password": "super-secret-pass"}) == {"password": "[REDACTED]"}
    assert redactor.redact({"secret_token": "token-123"}) == {"secret_token": "[REDACTED]"}

    # Check regular values remain unredacted
    assert redactor.redact({"stable_id": "hello"}) == {"stable_id": "hello"}

    # Check pattern-based redaction in strings
    assert redactor.redact("Here is my key: AKIAIOSFODNN7EXAMPLE") == "Here is my key: [REDACTED]"
    assert redactor.redact("ghp_123456789012345678901234567890123456") == "[REDACTED]"


def test_markdown_sanitization() -> None:
    renderer = SafeMarkdownRenderer()

    # Check basic formatting and dangerous tag escaping
    html = renderer.render("Hello <script>alert('xss')</script>")
    assert "alert('xss')" in html
    assert "<script>" not in html  # Script tag must be escaped

    # Check links validation
    safe_link = renderer.render("[Doc](https://path/to/doc.py)")
    assert 'href="https://path/to/doc.py"' in safe_link

    unsafe_link = renderer.render("[Email](mailto:test@example.com)")
    assert 'href="#"' in unsafe_link


def test_input_validation(tmp_path: Path) -> None:
    validator = InputValidator(tmp_path)

    # Clamping
    assert validator.validate_limit(150) == 100
    assert validator.validate_limit(50) == 50
    assert validator.validate_depth(20) == 10

    # Safe path traversal validation
    safe_path = validator.validate_safe_path("src/synapse/storage.py")
    assert safe_path.name == "storage.py"

    with pytest.raises(ValueError, match="Path traversal detected"):
        validator.validate_safe_path("../../outside.txt")

    # Suffix/prefix directory traversal edge case (e.g. synapse-malicious vs synapse)
    with pytest.raises(ValueError, match="Path traversal detected"):
        validator.validate_safe_path(Path(str(tmp_path) + "-malicious/outside.txt"))


@pytest.fixture
def mock_runtime(tmp_path: Path) -> SynapseRuntime:
    settings = SynapseSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synapse",
        profile=RuntimeProfile.DEV,
    )
    runtime = SynapseRuntime(settings)
    runtime.initialize_storage()
    return runtime


def test_api_endpoints(mock_runtime: SynapseRuntime) -> None:
    from synapse.api.app import create_app

    app = create_app(mock_runtime)
    client = TestClient(app)

    # Test status endpoint
    res = client.get("/api/v1/status")
    assert res.status_code == 200
    data = res.json()
    assert "repository_path" in data
    assert "events" in data

    # Test assumptions endpoint
    res = client.get("/api/v1/assumptions")
    assert res.status_code == 200
    assert "assumptions" in res.json()


def test_projection_engine(mock_runtime: SynapseRuntime) -> None:
    # Commit a dummy context so we have ancestry
    git_state = mock_runtime.git.state()
    semantic = mock_runtime.builder.manual_note(
        message="ADR decision: Use SQLite",
        branch="main",
        git_commit_hash=None,
    )

    from synapse.transactions.models import CognitionCommitRequest

    commit_res = mock_runtime.transaction_engine.commit_context_update(
        CognitionCommitRequest(
            operation="test_projection",
            event_type=EventType.MANUAL_NOTE_ADDED,
            source="manual://note",
            payload={"message": "ADR decision: Use SQLite"},
            actor="human",
            git_commit_hash=None,
            branch="main",
            parent_hashes=(),
            semantic_delta=(semantic,),
            summary="test note",
            provenance=semantic.provenance,
            confidence=semantic.confidence,
        )
    )

    context_hash = commit_res.context.object_hash
    engine = mock_runtime.projection_engine

    # Test Overview projection
    overview = engine.get_projection(context_hash, ProjectionKind.OVERVIEW)
    assert overview.context_hash == context_hash
    assert overview.kind == ProjectionKind.OVERVIEW

    # Test Replay projection
    replay = engine.get_projection(context_hash, ProjectionKind.REPLAY)
    assert replay.kind == ProjectionKind.REPLAY
    assert len(replay.nodes) == 1
    assert replay.nodes[0].id == context_hash
