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
        return LLMResponse(
            f"## Behavioral Summary\nRuntime behavior for {target}.\n\n## Edge Cases & Gotchas\nWatch out for race conditions in {target}.",
            10,
            10,
            0,
        )

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / ".env.example").write_text("SYNAP_LLM_PROVIDER=ollama\n")
    (repo / "main.py").write_text(
        '"""Main application entry point."""\n\n'
        'def hello(name: str = "world") -> str:\n'
        '    """Return greeting."""\n'
        '    return f"hello {name}"\n'
    )
    src_dir = repo / "src" / "pkg"
    src_dir.mkdir(parents=True)
    (src_dir / "service.py").write_text(
        '"""Service implementation."""\n\n'
        "import os\n\n"
        "class CoreService:\n"
        '    """Core processing service."""\n'
        "    def process(self, value: int) -> int:\n"
        "        return value * 2\n"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


def test_1_to_1_mirroring_directory_structure(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    result = runtime.wiki.generate(full=True)
    assert result["files"] >= 3

    # 1:1 mirroring paths directly under .synap/wiki/
    assert (runtime.wiki.wiki_dir / "main.py.md").exists()
    assert (runtime.wiki.wiki_dir / "src/pkg/service.py.md").exists()
    assert (runtime.wiki.wiki_dir / ".env.example.md").exists()

    # Never generate files/ prefix
    assert not (runtime.wiki.wiki_dir / "files").exists()

    # Never generate synthetic categories
    for synthetic in ("architecture", "flows", "concepts", "integrations", "modules"):
        assert not (runtime.wiki.wiki_dir / synthetic).exists()

    # Never generate synthetic index/tree/README files
    assert not (runtime.wiki.wiki_dir / "README.md").exists()
    assert not (runtime.wiki.wiki_dir / "codebase-tree.md").exists()
    assert not (runtime.wiki.wiki_dir / "file-index.md").exists()


def test_zero_llm_deterministic_generation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)

    # Insert an architectural decision impacting service.py
    with runtime.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO decisions (decision_id, branch, commit_hash, content, context, agent_id, created_at)
            VALUES ('dec-1', 'main', 'c0ffee1', 'Use CoreService for processing', 'src/pkg/service.py', 'builder', 1000)
            """
        )

    # Zero-LLM Mode A: provider is None
    runtime.wiki.provider = None
    result = runtime.wiki.generate(full=True)
    assert result["files"] >= 3
    assert not runtime.wiki.validate()
    assert runtime.wiki.status()["state"] == "fresh"

    # Verify main.py.md content
    main_doc = (runtime.wiki.wiki_dir / "main.py.md").read_text(encoding="utf-8")
    assert "Main application entry point." in main_doc
    assert "hello" in main_doc
    assert "def hello" in main_doc
    assert "Public Symbols & Interfaces" in main_doc
    assert "Imports & Dependencies" in main_doc
    assert "Callers & Callees" in main_doc
    assert "Architectural Decisions" in main_doc

    # Verify src/pkg/service.py.md content
    service_doc = (runtime.wiki.wiki_dir / "src/pkg/service.py.md").read_text(encoding="utf-8")
    assert "Service implementation." in service_doc
    assert "CoreService" in service_doc
    assert "class CoreService" in service_doc
    assert "import os" in service_doc
    assert "Use CoreService for processing" in service_doc


def test_deletion_of_orphaned_pages_and_empty_dirs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    # Add a temporary subfolder and file
    temp_dir = repo / "transient_module"
    temp_dir.mkdir(parents=True)
    (temp_dir / "worker.py").write_text("def work(): pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add worker"], cwd=repo, check=True, capture_output=True)

    runtime.wiki.generate(full=True)
    orphan_page = runtime.wiki.wiki_dir / "transient_module/worker.py.md"
    assert orphan_page.exists()

    # Remove source file and directory from repo
    subprocess.run(
        ["git", "rm", "-r", "transient_module"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "remove worker"], cwd=repo, check=True, capture_output=True
    )

    # Regenerating cleans up orphaned pages and removes empty directories
    runtime.wiki.generate(full=False)
    assert not orphan_page.exists()
    assert not (runtime.wiki.wiki_dir / "transient_module").exists()
    assert runtime.wiki.status()["state"] == "fresh"


def test_incremental_hash_based_caching(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    # 1. Full generation
    result_full = runtime.wiki.generate(full=True)
    total_files = result_full["files"]
    assert result_full["generated"] == total_files

    # 2. Incremental generation with no modifications -> 0 generated
    result_inc1 = runtime.wiki.generate(full=False)
    assert result_inc1["generated"] == 0

    # 3. Modify single file -> only 1 generated
    (repo / "main.py").write_text('def hello():\n    return "modified"\n')
    assert runtime.wiki.status()["state"] == "stale"
    assert "main.py" in runtime.wiki.status()["stale"]

    result_inc2 = runtime.wiki.generate(full=False)
    assert result_inc2["generated"] == 1
    assert runtime.wiki.status()["state"] == "fresh"

    # 4. Delete target .md file from disk -> regenerates missing file even if source hash is unchanged
    target_md = runtime.wiki.wiki_dir / "main.py.md"
    target_md.unlink()
    assert runtime.wiki.status()["state"] == "stale"

    result_inc3 = runtime.wiki.generate(full=False)
    assert result_inc3["generated"] == 1
    assert target_md.exists()
    assert runtime.wiki.status()["state"] == "fresh"


def test_path_traversal_rejection(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)

    with pytest.raises(ValueError, match="escapes"):
        runtime.wiki.ensure_wiki_page("files/../outside.py.md")

    with pytest.raises(ValueError, match="repository-relative"):
        runtime.wiki.ensure_wiki_page("/absolute/path.py")


def test_local_llm_augmentation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = FakeWikiProvider()  # type: ignore[assignment]

    result = runtime.wiki.generate(full=True)
    assert result["generated"] >= 3

    main_doc = (runtime.wiki.wiki_dir / "main.py.md").read_text(encoding="utf-8")
    assert "Behavioral Summary" in main_doc
    assert "Edge Cases & Gotchas" in main_doc
    assert "Public Symbols & Interfaces" in main_doc
