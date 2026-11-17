from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.provider.base import LLMResponse


class ValidTemplateWikiProvider:
    default_model = "test-local"

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
        target = user_prompt.split("Target: ", 1)[1].split("\n", 1)[0]
        # Valid template conforming to 8th-grade reading level and verified symbols
        content = (
            f"# {target}\n\n"
            f"**What it does:** Runs tests for `{target}`. It checks basic flow.\n\n"
            "**How it works**\n"
            "1. Starts the process.\n"
            "2. Finishes the work.\n\n"
            "**Key parts**\n"
            "- `hello`: Returns simple greeting.\n\n"
            "**Watch out for:** Keep inputs valid to avoid errors.\n"
        )
        return LLMResponse(content, 10, 10, 0)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


class HallucinatingWikiProvider:
    default_model = "test-local"

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
        # Hallucinates a symbol not in facts: `invented_fake_symbol_123`
        content = (
            "# target\n\n"
            "**What it does:** Invents symbols.\n\n"
            "**Key parts**\n"
            "- `invented_fake_symbol_123`: Fake function.\n"
        )
        return LLMResponse(content, 10, 10, 0)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / ".env.example").write_text(
        "SYNAP_LLM_PROVIDER=ollama\nSYNAP_SECRET_KEY=super_secret_token_12345\n"
    )
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

    # Verify main.py.md follows the fixed template and has fallback note
    main_doc = (runtime.wiki.wiki_dir / "main.py.md").read_text(encoding="utf-8")
    assert "*Note: Auto-extracted structural skeleton, no LLM summary.*" in main_doc
    assert "**What it does:**" in main_doc
    assert "**How it works**" in main_doc
    assert "**Key parts**" in main_doc
    assert "hello" in main_doc
    assert "Return greeting" in main_doc
    # main.py has no dependencies, so Connects to is skipped per template rules
    assert "**Connects to:**" not in main_doc
    assert "**Watch out for:**" in main_doc
    assert "**Recent changes:**" in main_doc

    # Verify src/pkg/service.py.md content, connections, and decisions
    service_doc = (runtime.wiki.wiki_dir / "src/pkg/service.py.md").read_text(encoding="utf-8")
    assert "*Note: Auto-extracted structural skeleton, no LLM summary.*" in service_doc
    assert "CoreService" in service_doc
    assert "Use CoreService for processing" in service_doc
    assert "**Connects to:**" in service_doc
    assert "os" in service_doc

    # Verify folder summary renders on demand without creating files
    folder_summary = runtime.wiki.get_folder_summary("src/pkg")
    assert "service.py" in folder_summary
    assert not (runtime.wiki.wiki_dir / "src/pkg/README.md").exists()


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


def test_local_llm_synthesis_and_validation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = ValidTemplateWikiProvider()  # type: ignore[assignment]

    result = runtime.wiki.generate(full=True)
    assert result["generated"] >= 3

    main_doc = (runtime.wiki.wiki_dir / "main.py.md").read_text(encoding="utf-8")
    assert "**What it does:**" in main_doc
    assert "**How it works**" in main_doc
    assert "**Key parts**" in main_doc
    # Should not have the fallback note since LLM synthesis succeeded
    assert "Auto-extracted structural skeleton" not in main_doc


def test_local_llm_validation_failure_fallback(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    # LLM hallucinates non-existent symbols -> validation fails and falls back to skeleton
    runtime.wiki.provider = HallucinatingWikiProvider()  # type: ignore[assignment]

    runtime.wiki.generate(full=True)
    main_doc = (runtime.wiki.wiki_dir / "main.py.md").read_text(encoding="utf-8")
    assert "*Note: Auto-extracted structural skeleton, no LLM summary.*" in main_doc
    assert "invented_fake_symbol_123" not in main_doc


def test_metadata_only_files_no_markdown_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    # Add a binary file, a lockfile, and a minified bundle
    (repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    (repo / "package-lock.json").write_text('{"name": "test-pkg", "lockfileVersion": 3}')
    (repo / "bundle.min.js").write_text("var a=1;console.log(a);")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add metadata files"], cwd=repo, check=True, capture_output=True
    )

    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    runtime.wiki.generate(full=True)

    # Markdown files must NOT exist for metadata-only files
    assert not (runtime.wiki.wiki_dir / "logo.png.md").exists()
    assert not (runtime.wiki.wiki_dir / "package-lock.json.md").exists()
    assert not (runtime.wiki.wiki_dir / "bundle.min.js.md").exists()

    # But 1-line metadata entries must exist in SQLite wiki_pages
    with runtime.store.connect() as conn:
        rows = conn.execute(
            "SELECT path, file_type, is_metadata, summary FROM wiki_pages WHERE is_metadata = 1 ORDER BY path"
        ).fetchall()
        meta_paths = {r["path"] for r in rows}
        assert "logo.png" in meta_paths
        assert "package-lock.json" in meta_paths
        assert "bundle.min.js" in meta_paths


def test_type_specific_extractors_and_secret_redaction(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    runtime.wiki.generate(full=True)

    env_doc = (runtime.wiki.wiki_dir / ".env.example.md").read_text(encoding="utf-8")
    # Secret values must be strictly redacted
    assert "super_secret_token_12345" not in env_doc
    assert "SYNAP_LLM_PROVIDER" in env_doc
    assert "**What it does:**" in env_doc
    assert "**Watch out for:**" in env_doc


def test_fts5_plain_english_retrieval(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    runtime.wiki.generate(full=True)

    # Search for plain-English query in FTS5
    results = runtime.wiki.search_wiki("greeting return")
    assert len(results) > 0
    matched_paths = [r["path"] for r in results]
    assert "main.py" in matched_paths
