from __future__ import annotations

from pathlib import Path

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.parser.registry import CodeParserRegistry
from synap_git.storage.sqlite import SynapStore


def test_eleven_language_import_extraction() -> None:
    """Validate that import extraction works across all 11 supported languages."""
    registry = CodeParserRegistry()

    samples = {
        "rust": (
            "src/main.rs",
            "use std::collections::HashMap;\nuse crate::models::User;\nfn main() {}",
        ),
        "java": (
            "src/Main.java",
            "import java.util.List;\nimport static org.junit.Assert.assertEquals;\nclass Main {}",
        ),
        "cpp": ("src/main.cpp", '#include <iostream>\n#include "my_header.h"\nint main() {}'),
        "c": ("src/main.c", '#include <stdio.h>\n#include "local.h"\nint main() {}'),
        "c_sharp": (
            "src/Program.cs",
            "using System;\nusing System.Collections.Generic;\nclass Program {}",
        ),
        "php": (
            "src/Index.php",
            "<?php\nuse App\\Models\\User;\nuse function App\\Helpers\\slugify;\nclass Index {}",
        ),
        "kotlin": (
            "src/Main.kt",
            "import java.util.ArrayList\nimport com.example.model.*\nclass Main {}",
        ),
        "scala": (
            "src/Main.scala",
            "import scala.collection.mutable.ArrayBuffer\nimport com.example.Foo\nclass Main {}",
        ),
        "ruby": ("src/main.rb", 'require "json"\nrequire_relative "models/user"\nclass Main; end'),
        "javascript": (
            "src/index.js",
            "import { foo } from './bar';\nconst qux = require('qux');\nfunction test() {}",
        ),
        "go": ("src/main.go", 'package main\nimport (\n\t"fmt"\n\t"net/http"\n)\nfunc main() {}'),
        "python": ("src/main.py", "import os\nfrom datetime import datetime\ndef main(): pass"),
    }

    for lang, (rel_path, code) in samples.items():
        res = registry.parse(Path(rel_path), relative_path=rel_path, text=code)
        assert len(res.imports) > 0, f"Expected non-empty imports for language {lang}"


def test_symbol_id_stability_across_blank_lines() -> None:
    """Validate that adding leading blank lines or comments does not alter symbol IDs."""
    registry = CodeParserRegistry()

    code_v1 = "def calculate_total(items):\n    return sum(items)\n"
    code_v2 = "\n\n# A new header comment\n\ndef calculate_total(items):\n    return sum(items)\n"

    res1 = registry.parse(Path("math.py"), relative_path="math.py", text=code_v1)
    res2 = registry.parse(Path("math.py"), relative_path="math.py", text=code_v2)

    assert len(res1.symbols) == 1
    assert len(res2.symbols) == 1
    sym1 = res1.symbols[0]
    sym2 = res2.symbols[0]

    assert sym1.name == sym2.name == "calculate_total"
    assert sym1.start_line == 1
    assert sym2.start_line == 5  # line shifted
    assert sym1.stable_id == sym2.stable_id, "stable_id should not change when line numbers shift"


def test_directed_graph_neighborhood(tmp_path: Path) -> None:
    """Validate that get_neighborhood supports downstream, upstream, and both directions."""
    db_path = tmp_path / "test.db"
    store = SynapStore(db_path)
    store.initialize()

    # Create files
    store.upsert_file_and_symbols(
        file_id="f1",
        path="caller.py",
        git_oid="oid1",
        content_hash="h1",
        language="python",
        symbols=[
            {
                "symbol_id": "sym_caller",
                "name": "caller_fn",
                "kind": "function",
                "start_line": 1,
                "end_line": 2,
                "ast_hash": "a1",
                "metadata": {},
            }
        ],
    )
    store.upsert_file_and_symbols(
        file_id="f2",
        path="callee.py",
        git_oid="oid2",
        content_hash="h2",
        language="python",
        symbols=[
            {
                "symbol_id": "sym_callee",
                "name": "callee_fn",
                "kind": "function",
                "start_line": 1,
                "end_line": 2,
                "ast_hash": "a2",
                "metadata": {},
            }
        ],
    )

    # Insert edge: caller -> callee
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO edges (edge_id, source_symbol, target_symbol, edge_type) VALUES (?, ?, ?, ?)",
            ("e1", "sym_caller", "sym_callee", "depends_on"),
        )

    # Downstream from caller should find callee
    downstream = store.get_neighborhood("sym_caller", depth=1, direction="downstream")
    down_ids = [r["symbol_id"] for r in downstream]
    assert "sym_callee" in down_ids

    # Downstream from callee should NOT find caller (directed!)
    callee_downstream = store.get_neighborhood("sym_callee", depth=1, direction="downstream")
    callee_down_ids = [r["symbol_id"] for r in callee_downstream]
    assert "sym_caller" not in callee_down_ids

    # Upstream from callee should find caller
    upstream = store.get_neighborhood("sym_callee", depth=1, direction="upstream")
    up_ids = [r["symbol_id"] for r in upstream]
    assert "sym_caller" in up_ids


def test_stdlib_filtering_and_bounded_graph_density(tmp_path: Path) -> None:
    """Validate that stdlib imports do not create clique edges to arbitrary internal symbols."""
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path, initial_branch="main")
    actor = git.Actor("Synap Test", "synapse@example.invalid")

    # File A defines a function named 'datetime'
    file_a = tmp_path / "models.py"
    file_a.write_text("def datetime():\n    return 'custom datetime'\n", encoding="utf-8")

    # File B imports standard library datetime and calls an unrelated function
    file_b = tmp_path / "service.py"
    file_b.write_text(
        "from datetime import datetime\ndef run_task():\n    pass\n", encoding="utf-8"
    )

    repo.index.add(["models.py", "service.py"])
    repo.index.commit("initial", author=actor, committer=actor)

    settings = SynapSettings(
        repository_path=tmp_path,
        state_path=tmp_path / ".synap",
        profile=RuntimeProfile.TEST,
    )
    runtime = SynapRuntime(settings)
    runtime.index_repository()

    # Check edges in database
    with runtime.store.connect() as conn:
        edges = conn.execute("SELECT * FROM edges").fetchall()
        # Since datetime is a standard library module, no fake edge should link run_task to models.py:datetime
        assert len(edges) == 0, f"Expected 0 edges for stdlib import, got: {len(edges)}"
