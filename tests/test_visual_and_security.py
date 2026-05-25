from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.context.objects import EventType
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

    # Test timeline endpoint
    res = client.get("/api/v1/timeline")
    assert res.status_code == 200
    assert "events" in res.json()


def test_projection_engine(mock_runtime: SynapseRuntime) -> None:
    git_state = mock_runtime.git.state()
    semantic = mock_runtime.builder.manual_note(
        message="ADR decision: Use SQLite",
        branch="main",
        git_commit_hash=None,
    )

    from synapse.transactions.models import ContextCommitRequest

    commit_res = mock_runtime.transaction_engine.commit_context_update(
        ContextCommitRequest(
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

    history = engine.get_projection(context_hash, ProjectionKind.HISTORY)
    assert history.kind == ProjectionKind.HISTORY
    assert len(history.nodes) == 1
    assert history.nodes[0].id == context_hash


def test_validation_state_properties() -> None:
    from synapse.context.objects import (
        Confidence,
        Provenance,
        SemanticKind,
        SemanticObject,
        SourceType,
        ValidationState,
        Validity,
    )

    provenance = Provenance(source_uri="test://uri", source_type=SourceType.CODE)

    # 1. Validated (confidence >= 0.85, active)
    obj1 = SemanticObject(
        stable_id="test1",
        kind=SemanticKind.ASSUMPTION,
        summary="Test assumption 1",
        provenance=provenance,
        confidence=Confidence(score=0.9, rationale="High evidence", evidence_count=5),
        validity=Validity(),
    )
    assert obj1.validation_state == ValidationState.VALIDATED

    # 2. Assumed (confidence < 0.85, active)
    obj2 = SemanticObject(
        stable_id="test2",
        kind=SemanticKind.ASSUMPTION,
        summary="Test assumption 2",
        provenance=provenance,
        confidence=Confidence(score=0.7, rationale="Medium evidence", evidence_count=1),
        validity=Validity(),
    )
    assert obj2.validation_state == ValidationState.ASSUMED

    # 3. Invalidated (validity valid_to_context set)
    obj3 = SemanticObject(
        stable_id="test3",
        kind=SemanticKind.ASSUMPTION,
        summary="Test assumption 3",
        provenance=provenance,
        confidence=Confidence(score=0.9, rationale="High evidence", evidence_count=5),
        validity=Validity(valid_to_context="some_context_hash"),
    )
    assert obj3.validation_state == ValidationState.INVALIDATED
