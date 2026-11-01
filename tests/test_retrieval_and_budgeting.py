from __future__ import annotations

from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


@pytest.fixture
def settings(tmp_path: Path) -> SynapSettings:
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
    return SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )


def test_hybrid_retrieval_order(settings: SynapSettings) -> None:
    runtime = SynapRuntime(settings)
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


def test_token_budgeting(settings: SynapSettings) -> None:
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Request a very small token budget
    # The system prompts + context blocks should be pruned
    answer, sources, trace = runtime.query_hybrid("How does login work?", max_tokens=700)

    # Trace should show elements and their token usage
    assert trace["tokens_used"] <= 700

    # Even with small budget, we should have at least the most relevant lexical match
    assert len(sources) > 0


def test_small_token_budget_graceful_folding(tmp_path: Path) -> None:
    """Verify that a small budget (e.g. 300 tokens) with a large function gracefully folds to AST skeleton."""
    repo = tmp_path / "budget_repo"
    repo.mkdir()
    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "budget@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Budget Tester"], cwd=repo, check=True)

    # Create a large function whose full snippet (~250 tokens) would exceed small retrieval budget
    heavy_code = [
        "def compute_heavy_metrics(data: list[int], threshold: float) -> dict[str, float]:",
        '    """Perform extensive metrics calculations on incoming dataset."""',
    ]
    for i in range(30):
        heavy_code.append(
            f"    temp_metric_{i} = sum(x * {i} for x in data) if threshold > {i} else 0.0"
        )
    heavy_code.append("    return {'total': sum(data), 'status': 1.0}")
    (repo / "metrics.py").write_text("\n".join(heavy_code), encoding="utf-8")

    (repo / "app.py").write_text(
        "from metrics import compute_heavy_metrics\ndef run():\n    return compute_heavy_metrics([1, 2], 0.5)\n",
        encoding="utf-8",
    )

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add heavy metrics"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap_budget.db",
        object_path=tmp_path / "objects_budget",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Small budget: 300 tokens
    # reserved_buffer = min(500, int(300 * 0.15)) = 45 tokens
    # retrieval_budget = 255 tokens
    # The full function block is > 255 tokens, so graceful folding must convert it to AST skeleton
    answer, sources, trace = runtime.query_hybrid("compute_heavy_metrics", max_tokens=300)

    assert len(sources) > 0
    assert trace["tokens_used"] <= 300
    assert trace["token_allocation"]["reserved_buffer"] == 45
    assert trace["token_allocation"]["retrieval_budget"] == 255

    # Answer should contain AST skeleton marker
    assert "[AST Skeleton]" in answer or any(
        "folded" in e.get("reason", "") for e in trace["elements"]
    )
    assert any(s["name"] == "compute_heavy_metrics" for s in sources)


def test_proportional_reserved_buffer_scaling(tmp_path: Path) -> None:
    """Verify reserved_buffer scales proportionally: min(500, int(max_tokens * 0.15))."""
    repo = tmp_path / "scale_repo"
    repo.mkdir()
    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "scale@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Scale Tester"], cwd=repo, check=True)
    (repo / "simple.py").write_text("def ping() -> str:\n    return 'pong'\n", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "init"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap_scale.db",
        object_path=tmp_path / "objects_scale",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Test 400 tokens -> buffer = 60
    _, _, trace_400 = runtime.query_hybrid("ping", max_tokens=400)
    assert trace_400["token_allocation"]["reserved_buffer"] == 60
    assert trace_400["token_allocation"]["retrieval_budget"] == 340

    # Test 600 tokens -> buffer = 90
    _, _, trace_600 = runtime.query_hybrid("ping", max_tokens=600)
    assert trace_600["token_allocation"]["reserved_buffer"] == 90
    assert trace_600["token_allocation"]["retrieval_budget"] == 510

    # Test 4000 tokens -> buffer = min(500, 600) = 500
    _, _, trace_4000 = runtime.query_hybrid("ping", max_tokens=4000)
    assert trace_4000["token_allocation"]["reserved_buffer"] == 500
    assert trace_4000["token_allocation"]["retrieval_budget"] == 3500
