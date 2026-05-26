from __future__ import annotations

from pathlib import Path

import pytest

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.indexer.engine import SynapseRuntime


def create_complex_repo(repo: Path) -> None:
    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "you@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Your Name"], cwd=repo, check=True)

    # Subsystem A
    (repo / "auth").mkdir()
    (repo / "auth" / "models.py").write_text(
        "class User:\n    def __init__(self, id: int): self.id = id"
    )
    (repo / "auth" / "service.py").write_text(
        "from .models import User\nclass AuthService:\n    def get_user(self, id: int) -> User: return User(id)"
    )

    # Subsystem B (depends on A)
    (repo / "api").mkdir()
    (repo / "api" / "handlers.py").write_text(
        "from auth.service import AuthService\ndef login_handler(id: int):\n    s = AuthService()\n    return s.get_user(id)"
    )

    # Main entry
    (repo / "main.py").write_text(
        "from api.handlers import login_handler\nif __name__ == '__main__':\n    login_handler(1)"
    )

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial"], cwd=repo, check=True)


@pytest.fixture
def complex_runtime(tmp_path: Path) -> SynapseRuntime:
    repo = tmp_path / "complex_repo"
    repo.mkdir()
    create_complex_repo(repo)

    settings = SynapseSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()
    return runtime


def test_grounding_accuracy_structural_hop(complex_runtime: SynapseRuntime) -> None:
    # If I ask about 'login_handler', it should find it and its direct dependency 'AuthService'
    _, sources, trace = complex_runtime.query_hybrid("Explain login_handler dependencies")

    source_names = {s["name"] for s in sources}
    source_paths = {s["source_path"] for s in sources}

    assert "login_handler" in source_names
    # Structural hop should find AuthService or at least the file it's in
    assert any("auth/service.py" in p for p in source_paths) or "AuthService" in source_names


def test_grounding_accuracy_lexical_match(complex_runtime: SynapseRuntime) -> None:
    # Query for 'User' - should find the User class
    _, sources, _ = complex_runtime.query_hybrid("What is the User model?")

    source_names = {s["name"] for s in sources}
    assert "User" in source_names


def test_retrieval_latency(complex_runtime: SynapseRuntime) -> None:
    # Basic performance check
    _, _, trace = complex_runtime.query_hybrid("How does the api work?")

    assert trace["latency_ms"] < 500  # Should be very fast for small repos
