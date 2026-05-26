from __future__ import annotations

from pathlib import Path

import pytest

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.indexer.engine import SynapseRuntime


@pytest.fixture
def settings(tmp_path: Path) -> SynapseSettings:
    repo = tmp_path / "repo"
    repo.mkdir()
    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "you@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Your Name"], cwd=repo, check=True)

    (repo / "auth.py").write_text("class Authenticator:\n    def login(self): pass")
    (repo / "main.py").write_text(
        "from auth import Authenticator\ndef run():\n    a = Authenticator()\n    a.login()"
    )

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial"], cwd=repo, check=True)
    return SynapseSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synapse.db",
        object_path=tmp_path / "objects",
    )


def test_hybrid_retrieval_order(settings: SynapseSettings) -> None:
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Search for 'login' - should find Authenticator and login method
    answer, sources, trace = runtime.query_hybrid("How does login work?", max_tokens=1000)

    assert len(sources) > 0
    # The first source should likely be the login method or Authenticator class (lexical match)
    source_names = [s["name"] for s in sources]
    assert "login" in source_names or "Authenticator" in source_names

    # Verify trace exists (PHASE 8)
    assert "trace_id" in trace
    assert trace["tokens_used"] > 0
    assert len(trace["elements"]) > 0


def test_token_budgeting(settings: SynapseSettings) -> None:
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    # Request a very small token budget
    # The system prompts + context blocks should be pruned
    answer, sources, trace = runtime.query_hybrid("How does login work?", max_tokens=700)

    # Trace should show elements and their token usage
    assert trace["tokens_used"] <= 700

    # Even with small budget, we should have at least the most relevant lexical match
    assert len(sources) > 0
