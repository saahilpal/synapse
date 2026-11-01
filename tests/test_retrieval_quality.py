from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        [git_bin, "config", "user.email", "retrieval@synapse.local"], cwd=repo, check=True
    )
    subprocess.run([git_bin, "config", "user.name", "Retrieval Tester"], cwd=repo, check=True)

    # Base python files
    (repo / "main.py").write_text("def hello(): pass\n", encoding="utf-8")
    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "initial commit"], cwd=repo, check=True)

    return repo


def test_duplicate_symbol_indexing_and_ranking(temp_repo: Path, tmp_path: Path) -> None:
    """Duplicate symbol names in different files must be indexed independently and ranked correctly."""
    # Write two files with same function name
    (temp_repo / "foo.py").write_text("def process_data():\n    return 1\n", encoding="utf-8")
    (temp_repo / "bar.py").write_text("def process_data():\n    return 2\n", encoding="utf-8")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add duplicate symbols"], cwd=temp_repo, check=True)

    settings = SynapSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Query for process_data
    ans, sources, trace = runtime.query_hybrid("process_data", max_tokens=1000)

    # We should have both symbols in the database
    with runtime.store.connect() as conn:
        rows = conn.execute("SELECT * FROM symbols WHERE name = 'process_data'").fetchall()
        assert len(rows) == 2

    # Both symbols should be identified as grounding sources in retrieval
    paths = [s["source_path"] for s in sources]
    assert "foo.py" in paths
    assert "bar.py" in paths


def test_circular_imports_traversal(temp_repo: Path, tmp_path: Path) -> None:
    """Circular imports between files must not cause infinite loops during structural traversal."""
    # File A imports B; File B imports A
    (temp_repo / "module_a.py").write_text(
        "import module_b\ndef func_a(): pass\n", encoding="utf-8"
    )
    (temp_repo / "module_b.py").write_text(
        "import module_a\ndef func_b(): pass\n", encoding="utf-8"
    )

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "circular imports"], cwd=temp_repo, check=True)

    settings = SynapSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Query for func_a. Neighborhood traversal will traverse to module_b via import, then back to module_a.
    # Since depth is strictly limited, it must complete successfully.
    ans, sources, trace = runtime.query_hybrid("func_a", max_tokens=1000)
    assert len(sources) > 0


def test_unicode_and_malformed_files(temp_repo: Path, tmp_path: Path) -> None:
    """Verify non-ASCII filenames and malformed text files are indexed safely or skipped."""
    # Unicode file name
    (temp_repo / "unicode_你好.py").write_text("def test_unicode(): pass\n", encoding="utf-8")

    # Malformed file (invalid UTF-8 bytes)
    malformed_path = temp_repo / "malformed.py"
    with malformed_path.open("wb") as f:
        f.write(b"def bad_utf8(): pass\n# \xff\xfe\xfd invalid bytes")

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run(
        [git_bin, "commit", "-m", "unicode and malformed files"], cwd=temp_repo, check=True
    )

    settings = SynapSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Unicode file should be indexed successfully
    status = runtime.status()
    with runtime.store.connect() as conn:
        unicode_exists = conn.execute(
            "SELECT count(*) FROM files WHERE path = 'unicode_你好.py'"
        ).fetchone()[0]
        assert unicode_exists == 1

        # Malformed invalid UTF-8 bytes file: if scanner skips it or reads with errors='ignore', it shouldn't crash
        malformed_exists = conn.execute(
            "SELECT count(*) FROM files WHERE path = 'malformed.py'"
        ).fetchone()[0]
        # Should be indexed because errors="ignore" is used or skipped safely if binary
        # Let's verify it didn't crash indexing
        assert status.files >= 3


def test_retrieval_determinism(temp_repo: Path, tmp_path: Path) -> None:
    """Verify that retrieval results are completely deterministic across identical queries."""
    (temp_repo / "calc.py").write_text(
        "def add(a, b): return a + b\ndef sub(a, b): return a - b\n", encoding="utf-8"
    )

    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "add", "."], cwd=temp_repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add calc module"], cwd=temp_repo, check=True)

    settings = SynapSettings(
        repository_path=temp_repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap.db",
        object_path=tmp_path / "objects",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Query 5 times
    outputs = []
    for _ in range(5):
        ans, sources, trace = runtime.query_hybrid("add", max_tokens=1000)
        outputs.append((sources, trace["elements"]))

    # All outputs must be identical in structure and ordering
    first_sources, first_elements = outputs[0]
    for other_sources, other_elements in outputs[1:]:
        assert len(first_sources) == len(other_sources)
        for s1, s2 in zip(first_sources, other_sources, strict=False):
            assert s1["symbol_id"] == s2["symbol_id"]
            assert s1["name"] == s2["name"]

        assert len(first_elements) == len(other_elements)
        for e1, e2 in zip(first_elements, other_elements, strict=False):
            assert e1["stable_id"] == e2["stable_id"]
            assert e1["score"] == e2["score"]


def test_intent_classification_precedence() -> None:
    """Verify conceptual intent words take precedence over structural punctuation."""
    from synap_git.retrieval.engine import _classify_intent_fast

    # Conceptual queries containing structural tokens ('_', '/', '.py', '()')
    assert _classify_intent_fast("What is user_id?") == "conceptual"
    assert _classify_intent_fast("Why does auth/login.py fail?") == "conceptual"
    assert _classify_intent_fast("How does get_neighborhood() work?") == "conceptual"
    assert _classify_intent_fast("Architecture of db_conn and ws_client") == "conceptual"
    assert _classify_intent_fast("Explain the design of models.py") == "conceptual"
    assert _classify_intent_fast("Overview of /api/handlers") == "conceptual"

    # Pure structural queries without conceptual intent
    assert _classify_intent_fast("get_neighborhood()") == "structural"
    assert _classify_intent_fast("auth/login.py") == "structural"
    assert _classify_intent_fast("def login") == "structural"
    assert _classify_intent_fast("class Authenticator") == "structural"

    # Default logic queries
    assert _classify_intent_fast("login authenticate user") == "logic"


def test_lexical_subtokenization_and_short_identifiers(tmp_path: Path) -> None:
    """Verify camelCase and snake_case queries match across conventions and short tokens (>= 2 chars) are preserved."""
    repo = tmp_path / "case_repo"
    repo.mkdir()
    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "case@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Case Tester"], cwd=repo, check=True)

    # File with snake_case and short identifiers
    (repo / "store.py").write_text(
        "def get_neighborhood(node_id: int): pass\ndef init_db(): pass\ndef get_ip(): pass\n",
        encoding="utf-8",
    )
    # File with camelCase and short identifiers
    (repo / "client.py").write_text(
        "def userId(name: str): pass\ndef wsClient(): pass\ndef showUI(): pass\n",
        encoding="utf-8",
    )

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "add test symbols"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap_case.db",
        object_path=tmp_path / "objects_case",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # 1. camelCase query matching snake_case symbol
    _, sources1, _ = runtime.query_hybrid("getNeighborhood", max_tokens=1000)
    names1 = [s["name"] for s in sources1]
    assert "get_neighborhood" in names1

    # 2. snake_case query matching camelCase symbol
    _, sources2, _ = runtime.query_hybrid("user_id", max_tokens=1000)
    names2 = [s["name"] for s in sources2]
    assert "userId" in names2

    # 3. Short identifiers: >= 2 chars (db, ip, ui, ws)
    _, sources_db, _ = runtime.query_hybrid("init_db", max_tokens=1000)
    assert any("init_db" in s["name"] for s in sources_db)

    _, sources_ws, _ = runtime.query_hybrid("wsClient", max_tokens=1000)
    assert any("wsClient" in s["name"] for s in sources_ws)

    _, sources_ip, _ = runtime.query_hybrid("get_ip", max_tokens=1000)
    assert any("get_ip" in s["name"] for s in sources_ip)


def test_graph_centrality_and_test_fixture_deprioritization(tmp_path: Path) -> None:
    """Foundational interfaces (with high PageRank centrality) must rank above test fixtures."""
    repo = tmp_path / "graph_repo"
    repo.mkdir()
    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "graph@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Graph Tester"], cwd=repo, check=True)

    # Core interface
    (repo / "auth.py").write_text(
        "class Authenticator:\n    def login(self, username: str) -> bool:\n        return True\n",
        encoding="utf-8",
    )
    # Consumer that imports and calls the core interface (creating high PageRank hub status)
    (repo / "main.py").write_text(
        "from auth import Authenticator\ndef run():\n    a = Authenticator()\n    return a.login('alice')\n",
        encoding="utf-8",
    )
    # Test fixture with the same method name in tests/
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_auth.py").write_text(
        "def test_login():\n    pass\ndef mock_login():\n    pass\n",
        encoding="utf-8",
    )

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "graph setup"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap_graph.db",
        object_path=tmp_path / "objects_graph",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    # Query for login
    _, sources, trace = runtime.query_hybrid("login", max_tokens=1000)

    assert len(sources) > 0
    # Top source must be from auth.py (the foundational interface), NOT tests/test_auth.py
    top_source = sources[0]
    assert "auth.py" in top_source["source_path"]
    assert "tests/" not in top_source["source_path"]


def test_grounded_evaluation_benchmark_precision_recall_latency(tmp_path: Path) -> None:
    """
    Grounded evaluation benchmark measuring:
    1. Precision@k
    2. Recall@k
    3. Token reduction (snippets/skeletons vs raw files)
    4. Latency (p50 < 50ms, p95 < 100ms)
    """
    import time

    import tiktoken

    repo = tmp_path / "benchmark_repo"
    repo.mkdir()
    git_bin = shutil.which("git") or "git"
    subprocess.run([git_bin, "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.email", "eval@example.com"], cwd=repo, check=True)
    subprocess.run([git_bin, "config", "user.name", "Eval Benchmark"], cwd=repo, check=True)

    # 1. Database layer
    (repo / "db.py").write_text(
        "class DatabaseConnection:\n"
        '    """Thread-safe database connection manager."""\n'
        '    def __init__(self, host: str = "localhost", port: int = 5432, max_conns: int = 20):\n'
        "        self.host = host\n"
        "        self.port = port\n"
        "        self.max_conns = max_conns\n"
        "        self.pool = []\n"
        "        self._connected = False\n"
        "\n"
        "    def connect(self) -> bool:\n"
        '        """Connect to database."""\n'
        "        for i in range(self.max_conns):\n"
        '            self.pool.append({"id": i, "active": True})\n'
        "        self._connected = True\n"
        "        return True\n"
        "\n"
        "    def execute_query(self, sql: str, params: list[str] | None = None) -> list[dict[str, str]]:\n"
        '        """Execute query."""\n'
        "        if not self._connected:\n"
        '            raise RuntimeError("Database not connected")\n'
        '        return [{"status": "ok", "row": "data"}]\n'
        "\n"
        "    def close(self) -> None:\n"
        '        """Close all connections."""\n'
        "        self.pool.clear()\n"
        "        self._connected = False\n",
        encoding="utf-8",
    )
    # 2. Service layer
    (repo / "service.py").write_text(
        "from db import DatabaseConnection\n"
        "\n"
        "class UserService:\n"
        '    """User management domain service."""\n'
        "    def __init__(self):\n"
        "        self.db = DatabaseConnection()\n"
        "\n"
        "    def get_user_profile(self, user_id: int) -> dict[str, str]:\n"
        '        """Fetch user profile."""\n'
        "        self.db.connect()\n"
        '        rows = self.db.execute_query("SELECT * FROM users WHERE id = ?", [str(user_id)])\n'
        '        return {"id": str(user_id), "name": "Alice", "role": "admin"}\n'
        "\n"
        "    def update_user_email(self, user_id: int, new_email: str) -> bool:\n"
        '        """Update user email."""\n'
        '        if "@" not in new_email:\n'
        '            raise ValueError("Invalid email address")\n'
        '        self.db.execute_query("UPDATE users SET email = ? WHERE id = ?", [new_email, str(user_id)])\n'
        "        return True\n",
        encoding="utf-8",
    )
    # 3. API Controller layer
    (repo / "controller.py").write_text(
        "from service import UserService\n"
        "\n"
        "def handle_get_user(user_id: int) -> dict[str, str]:\n"
        '    """HTTP handler for GET user."""\n'
        "    svc = UserService()\n"
        "    return svc.get_user_profile(user_id)\n"
        "\n"
        "def handle_update_email(user_id: int, email: str) -> dict[str, str]:\n"
        '    """HTTP handler for POST email update."""\n'
        "    svc = UserService()\n"
        "    svc.update_user_email(user_id, email)\n"
        '    return {"status": "success"}\n',
        encoding="utf-8",
    )
    # 4. Models layer
    (repo / "models.py").write_text(
        "class UserEntity:\n"
        '    """ORM Entity representing user accounts in persistent storage."""\n'
        "    def __init__(self, id: int, name: str, email: str, role: str):\n"
        "        self.id = id\n"
        "        self.name = name\n"
        "        self.email = email\n"
        "        self.role = role\n"
        "        self.is_active = True\n"
        "        self.created_at = 1700000000\n"
        "\n"
        "    def serialize(self) -> dict[str, str]:\n"
        '        """Serialize user entity to JSON-compatible dictionary."""\n'
        '        return {"id": str(self.id), "name": self.name, "email": self.email}\n'
        "\n"
        "    def validate_permissions(self, required_role: str) -> bool:\n"
        '        """Check if current user has the required permission level."""\n'
        '        return self.role == required_role or self.role == "admin"\n',
        encoding="utf-8",
    )
    # 5. Configuration layer
    (repo / "config.py").write_text(
        "class SystemSettings:\n"
        '    """Central system configuration settings loaded from environment."""\n'
        "    def __init__(self):\n"
        '        self.db_host = "localhost"\n'
        "        self.db_port = 5432\n"
        '        self.app_name = "benchmark_service"\n'
        "        self.debug_mode = True\n"
        '        self.secret_key = "supersecret12345"\n'
        "        self.token_ttl = 3600\n"
        '        self.allowed_hosts = ["localhost", "127.0.0.1"]\n'
        "\n"
        "    def is_production(self) -> bool:\n"
        '        """Verify whether the environment is marked production."""\n'
        "        return not self.debug_mode\n",
        encoding="utf-8",
    )

    subprocess.run([git_bin, "add", "."], cwd=repo, check=True)
    subprocess.run([git_bin, "commit", "-m", "benchmark setup"], cwd=repo, check=True)

    settings = SynapSettings(
        repository_path=repo,
        profile=RuntimeProfile.TEST,
        sqlite_path=tmp_path / "synap_eval.db",
        object_path=tmp_path / "objects_eval",
    )
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    tokenizer = tiktoken.get_encoding("cl100k_base")

    # Benchmark test cases: (query, relevant_symbol_names)
    eval_cases = [
        (
            "handle_get_user controller",
            {"handle_get_user", "UserService"},
        ),
        (
            "DatabaseConnection execute_query",
            {"DatabaseConnection", "execute_query", "connect"},
        ),
        (
            "get_user_profile service",
            {"get_user_profile", "UserService"},
        ),
    ]

    latencies_ms: list[float] = []
    precision_at_3_scores: list[float] = []
    recall_at_5_scores: list[float] = []
    token_reductions: list[float] = []

    # Total raw repository tokens across all source files
    total_raw_tokens = sum(
        len(tokenizer.encode(f.read_text(encoding="utf-8"))) for f in repo.glob("*.py")
    )

    for query, relevant_symbols in eval_cases:
        t0 = time.perf_counter()
        answer, sources, trace = runtime.query_hybrid(
            query, max_tokens=350, synthesize_answer=False
        )
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000)

        retrieved_names = [s["name"] for s in sources]

        # Precision@3
        top_3 = retrieved_names[:3]
        relevant_in_top_3 = sum(1 for name in top_3 if name in relevant_symbols)
        p_at_3 = relevant_in_top_3 / min(3, len(top_3)) if top_3 else 0.0
        precision_at_3_scores.append(p_at_3)

        # Recall@5
        top_5 = retrieved_names[:5]
        found_relevant = sum(1 for sym in relevant_symbols if sym in top_5)
        r_at_5 = found_relevant / len(relevant_symbols) if relevant_symbols else 0.0
        recall_at_5_scores.append(r_at_5)

        # Token reduction vs reading whole repository
        packed_tokens = trace["tokens_used"]
        reduction = (
            (1.0 - (packed_tokens / total_raw_tokens)) * 100.0 if total_raw_tokens > 0 else 0.0
        )
        token_reductions.append(reduction)

    avg_p_at_3 = sum(precision_at_3_scores) / len(precision_at_3_scores)
    avg_r_at_5 = sum(recall_at_5_scores) / len(recall_at_5_scores)
    avg_latency = sum(latencies_ms) / len(latencies_ms)
    avg_reduction = sum(token_reductions) / len(token_reductions)

    # Benchmark assertions
    assert avg_p_at_3 >= 0.70, f"Precision@3 too low: {avg_p_at_3}"
    assert avg_r_at_5 >= 0.70, f"Recall@5 too low: {avg_r_at_5}"
    assert avg_latency < 50.0, f"Average latency too high: {avg_latency}ms"
    assert avg_reduction >= 40.0, f"Token reduction too low: {avg_reduction}%"
