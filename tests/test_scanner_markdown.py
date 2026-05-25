from __future__ import annotations

from pathlib import Path

from synapse.context.markdown import MarkdownContextExtractor
from synapse.context.objects import SemanticKind
from synapse.context.scanner import RepositoryScanner


def test_scanner_and_markdown_extractor_find_context_annotations(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Architecture\n\n"
        "The runtime must keep MCP as an interface, not the brain.\n\n"
        "## Risks\n\n"
        "Risk: docs can drift from code.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = ['pydantic>=2']\n",
        encoding="utf-8",
    )

    scan = RepositoryScanner(repository_path=tmp_path).scan()
    objects = MarkdownContextExtractor().extract_scan(scan)

    assert scan.language_counts["markdown"] == 1
    assert scan.dependencies == ("pydantic",)
    assert {obj.kind for obj in objects} >= {SemanticKind.ARCHITECTURE, SemanticKind.RISK}
