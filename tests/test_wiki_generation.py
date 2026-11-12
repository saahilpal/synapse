from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.provider.base import LLMResponse


class FakeWikiProvider:
    default_model = "test-local"

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
        target = user_prompt.split("Target: ", 1)[1].split("\n", 1)[0]
        diagram = (
            "\n```mermaid\nflowchart TD\n A[Evidence] --> B[Documentation]\n```\n"
            if target.startswith("flows/")
            else ""
        )
        return LLMResponse(f"# {target}\n\nEvidence-grounded documentation.{diagram}", 1, 1, 0)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / ".env.example").write_text("SYNAP_LLM_PROVIDER=ollama\n")
    (repo / "main.py").write_text("def hello():\n    return 'hi'\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


def test_full_and_incremental_wiki_generation(tmp_path: Path) -> None:
    runtime = SynapRuntime(
        SynapSettings(repository_path=_repo(tmp_path), profile=RuntimeProfile.TEST)
    )
    runtime.bootstrap(force=True)
    runtime.wiki.provider = FakeWikiProvider()  # type: ignore[assignment]

    result = runtime.wiki.generate(full=True)
    assert result["files"] >= 2
    tree = runtime.wiki.wiki_dir / "codebase-tree.md"
    assert "main.py" in tree.read_text()
    assert (runtime.wiki.wiki_dir / "files/main.py.md").exists()
    assert not runtime.wiki.validate()
    assert runtime.wiki.status()["state"] == "fresh"

    (runtime.settings.repository_path / "main.py").write_text(
        "def hello():\n    return 'changed'\n"
    )
    assert runtime.wiki.status()["state"] == "stale"
    result = runtime.wiki.generate(full=False)
    assert result["generated"] == 1
    assert runtime.wiki.status()["state"] == "fresh"


def test_unavailable_local_model_preserves_existing_pages(tmp_path: Path) -> None:
    runtime = SynapRuntime(
        SynapSettings(repository_path=_repo(tmp_path), profile=RuntimeProfile.TEST)
    )
    runtime.bootstrap(force=True)
    target = runtime.wiki.wiki_dir / "files/main.py.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Existing\n")
    runtime.wiki.provider = None
    with pytest.raises(RuntimeError, match="Local LLM is unavailable"):
        runtime.wiki.generate(full=True)
    assert target.read_text() == "# Existing\n"


def test_deleted_source_is_stale_and_traversal_is_rejected(tmp_path: Path) -> None:
    runtime = SynapRuntime(
        SynapSettings(repository_path=_repo(tmp_path), profile=RuntimeProfile.TEST)
    )
    runtime.bootstrap(force=True)
    runtime.wiki.provider = FakeWikiProvider()  # type: ignore[assignment]
    runtime.wiki.generate(full=True)
    (runtime.settings.repository_path / "main.py").unlink()
    status = runtime.wiki.status()
    assert status["state"] == "stale"
    assert "main.py" in status["stale"]
    with pytest.raises(ValueError, match="escapes"):
        runtime.wiki.ensure_wiki_page("files/../outside.py.md")
