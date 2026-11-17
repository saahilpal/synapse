from __future__ import annotations

import subprocess
from pathlib import Path

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "grounding_repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    return repo


def _commit_all(repo: Path, message: str = "commit") -> None:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def test_cursorrules_wiki_generation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / ".cursorrules").write_text(
        "# Code Quality Guidelines\n"
        "- Always use strict type annotations with mypy\n"
        "- Never swallow exceptions without logging\n"
        "- Enforce line length of 100 with ruff\n\n"
        "# Testing Standards\n"
        "- Run pytest before pushing commits\n"
    )
    _commit_all(repo, "add cursorrules")

    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    result = runtime.wiki.generate(full=True)
    assert result["files"] >= 1

    wiki_file = runtime.wiki.wiki_dir / ".cursorrules.md"
    assert wiki_file.exists()
    doc = wiki_file.read_text(encoding="utf-8")

    # Verify classification in SQLite
    with runtime.store.connect() as conn:
        row = conn.execute(
            "SELECT file_type FROM wiki_pages WHERE path = '.cursorrules'"
        ).fetchone()
        assert row is not None
        assert row["file_type"] == "config_rules"

    # Verify extracted facts are cited
    assert "mypy" in doc or "strict type" in doc
    assert "pytest" in doc
    assert "exceptions" in doc or "logging" in doc
    assert "Code Quality Guidelines" in doc or "Testing Standards" in doc

    # Verify zero generic filler sentences
    assert "Imports needed files" not in doc
    assert "Runs code through public functions" not in doc
    assert "Sends back results" not in doc
    assert "Reads settings and environment" not in doc
    assert "Sets runtime options for the system" not in doc

    # Completeness and validation
    validation_errors = runtime.wiki.validate()
    assert not validation_errors


def test_dockerfile_wiki_generation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "Dockerfile").write_text(
        "FROM python:3.12-slim AS builder\n"
        "WORKDIR /app\n"
        "ENV PORT=8000\n"
        "EXPOSE 8000\n"
        "RUN pip install -r requirements.txt\n"
        'CMD ["python", "main.py"]\n'
    )
    _commit_all(repo, "add dockerfile")

    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    runtime.wiki.generate(full=True)
    wiki_file = runtime.wiki.wiki_dir / "Dockerfile.md"
    assert wiki_file.exists()
    doc = wiki_file.read_text(encoding="utf-8")

    # Verify extracted facts
    assert "builder" in doc or "python:3.12-slim" in doc
    assert "PORT" in doc
    assert "8000" in doc
    assert "pip install" in doc
    assert "CMD" in doc

    # Verify zero generic filler
    assert "Reads settings and environment variables" not in doc
    assert "Sets runtime options for the system" not in doc
    assert "Imports needed files" not in doc

    assert not runtime.wiki.validate()


def test_yaml_workflow_wiki_generation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "name: CI\n"
        "on: [push, pull_request]\n"
        "jobs:\n"
        "  lint:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - run: ruff check .\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    services:\n"
        "      redis:\n"
        "        image: redis:alpine\n"
        "        ports:\n"
        "          - 6379:6379\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - run: pytest -v\n"
    )
    _commit_all(repo, "add ci workflow")

    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    runtime.wiki.generate(full=True)
    wiki_file = runtime.wiki.wiki_dir / ".github/workflows/ci.yml.md"
    assert wiki_file.exists()
    doc = wiki_file.read_text(encoding="utf-8")

    # Verify extracted facts
    assert "lint" in doc
    assert "test" in doc
    assert "redis" in doc
    assert "ruff check" in doc or "pytest" in doc

    # Verify zero generic filler
    assert "Reads settings and environment variables" not in doc
    assert "Sets runtime options for the system" not in doc

    assert not runtime.wiki.validate()


def test_test_file_wiki_generation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    src_dir = repo / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "calculator.py").write_text(
        "class Calculator:\n    def add(self, a: int, b: int) -> int:\n        return a + b\n"
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_calculator.py").write_text(
        "import pytest\n"
        "from src.calculator import Calculator\n\n"
        "@pytest.fixture\n"
        "def sample_calc():\n"
        "    return Calculator()\n\n"
        "def test_add_numbers(sample_calc):\n"
        "    assert sample_calc.add(2, 3) == 5\n\n"
        "def test_divide_zero(sample_calc):\n"
        "    pass\n"
    )
    _commit_all(repo, "add calculator and tests")

    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    runtime.wiki.generate(full=True)
    wiki_file = runtime.wiki.wiki_dir / "tests/test_calculator.py.md"
    assert wiki_file.exists()
    doc = wiki_file.read_text(encoding="utf-8")

    # Verify extracted facts
    assert "test_add_numbers" in doc
    assert "sample_calc" in doc
    assert "src/calculator.py" in doc or "Calculator" in doc

    # Verify zero generic filler
    assert "Sets up test fixtures and required mocks" not in doc
    assert "Executes test scenarios against target functions" not in doc
    assert "Asserts expected outcomes and error handling" not in doc

    assert not runtime.wiki.validate()


def test_python_source_file_wiki_generation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    src_dir = repo / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "calculator.py").write_text(
        '"""Core arithmetic calculator engine."""\n'
        "import math\n\n"
        "class Calculator:\n"
        '    """Arithmetic calculation handler."""\n'
        "    def add(self, a: int, b: int) -> int:\n"
        '        """Sum two numbers."""\n'
        "        return a + b\n\n"
        "    def divide(self, a: int, b: int) -> float:\n"
        '        """Divide numbers."""\n'
        "        return a / b\n"
    )
    _commit_all(repo, "add calculator source")

    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)
    runtime.wiki.provider = None

    runtime.wiki.generate(full=True)
    wiki_file = runtime.wiki.wiki_dir / "src/calculator.py.md"
    assert wiki_file.exists()
    doc = wiki_file.read_text(encoding="utf-8")

    # Verify extracted facts
    assert "Calculator" in doc
    assert "add" in doc or "divide" in doc
    assert "math" in doc

    # Verify zero generic filler
    assert "Imports needed files and helper tools" not in doc
    assert "Runs code through public functions and classes" not in doc
    assert "Sends back results to callers" not in doc

    assert not runtime.wiki.validate()


def test_generic_filler_fails_validation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "dummy.py").write_text("x = 1\n")
    _commit_all(repo, "dummy")
    runtime = SynapRuntime(SynapSettings(repository_path=repo, profile=RuntimeProfile.TEST))
    runtime.bootstrap(force=True)

    facts = {
        "path": "src/module.py",
        "file_type": "source_code",
        "is_metadata": False,
        "what_it_does": "Source code module for src/module.py.",
        "summary": "Source code module for src/module.py.",
        "how_it_works": ["Step 1."],
        "key_parts": [("run", "Runs processing.")],
        "connects_to": [],
        "watch_out_for": "Check caller files.",
        "recent_changes": [],
        "all_known_symbols": {"run", "execute"},
        "all_repo_paths": {"src/module.py"},
    }

    # 1. Page with generic boilerplate phrases must fail
    boilerplate_page = (
        "# src/module.py\n\n"
        "**What it does:** Runs code.\n\n"
        "**How it works**\n"
        "1. Imports needed files and helper tools.\n"
        "2. Runs code through public functions and classes.\n"
        "3. Sends back results to callers.\n\n"
        "**Key parts**\n"
        "- `run`: Runs processing.\n\n"
        "**Watch out for:** Check caller files.\n"
    )
    errors = runtime.wiki._validate_page(boilerplate_page, facts)
    assert any("Generic boilerplate detected" in e for e in errors)

    # 2. Page lacking specific symbol/directive citation must fail specificity check
    ungrounded_page = (
        "# src/module.py\n\n"
        "**What it does:** Plain prose without mentioning any extracted facts.\n\n"
        "**How it works**\n"
        "1. Starts up silently.\n"
        "2. Finishes up without mentioning any code identifiers.\n\n"
        "**Key parts**\n"
        "- `python`: Standard runtime.\n\n"
        "**Watch out for:** Keep inputs valid.\n"
    )
    errors2 = runtime.wiki._validate_page(ungrounded_page, facts)
    assert any("Page lacks specificity" in e for e in errors2)
