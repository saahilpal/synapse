"""Tests for Agent Compatibility Matrix, Agent Detection, and SKILL.md Token Budget."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import tiktoken

from synap_git.cli.skill_installer import (
    SYNAP_END_MARKER,
    SYNAP_START_MARKER,
    detect_installed_agents,
    get_compatibility_matrix,
    get_skill_template,
    install_skills,
)


def test_compatibility_matrix_completeness() -> None:
    """Validate all 10 agents exist in matrix with required paths and statuses."""
    matrix = get_compatibility_matrix()
    assert len(matrix) == 10

    expected_agents = {
        "claude": ("Claude Code", "tested end-to-end", ".claude/skills/synap/SKILL.md"),
        "cursor": ("Cursor", "tested end-to-end", ".cursor/rules/synap.mdc"),
        "codex": ("Codex CLI", "tested end-to-end", "AGENTS.md"),
        "gemini": ("Gemini CLI", "tested end-to-end", "AGENTS.md"),
        "copilot": ("GitHub Copilot", "tested end-to-end", ".github/copilot-instructions.md"),
        "windsurf": ("Windsurf", "tested end-to-end", ".windsurfrules"),
        "cline": ("Cline / Roo Code", "tested end-to-end", ".clinerules"),
        "aider": ("Aider", "generated, untested", ".aider.conf.yml"),
        "continue": ("Continue", "generated, untested", ".continue/config.json"),
        "zed": ("Zed", "generated, untested", ".zed/settings.json"),
    }

    matrix_by_id = {item["id"]: item for item in matrix}
    for agent_id, (expected_name, expected_status, primary_path) in expected_agents.items():
        assert agent_id in matrix_by_id, f"Missing agent {agent_id} in matrix"
        agent = matrix_by_id[agent_id]
        assert agent["name"] == expected_name
        assert agent["status"] == expected_status
        assert primary_path in agent["config_paths"]


def test_agent_detection_filesystem(tmp_path: Path) -> None:
    """Test filesystem-based detection of installed agents."""
    with patch("shutil.which", return_value=None):
        # Empty repo -> no agents detected
        assert len(detect_installed_agents(tmp_path)) == 0

        # Create Cursor folder
        (tmp_path / ".cursor").mkdir()
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "cursor" for a in detected)

        # Create Claude Code instructions
        (tmp_path / "CLAUDE.md").write_text("# Claude Rules\n", encoding="utf-8")
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "claude" for a in detected)

        # Create GitHub Copilot instructions
        (tmp_path / ".github").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".github" / "copilot-instructions.md").write_text("Copilot\n", encoding="utf-8")
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "copilot" for a in detected)

        # Create Windsurf rules
        (tmp_path / ".windsurfrules").write_text("# Windsurf\n", encoding="utf-8")
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "windsurf" for a in detected)

        # Create Cline rules
        (tmp_path / ".clinerules").write_text("# Cline\n", encoding="utf-8")
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "cline" for a in detected)

        # Create Aider config
        (tmp_path / ".aider.conf.yml").write_text("model: sonnet\n", encoding="utf-8")
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "aider" for a in detected)

        # Create Continue config folder
        (tmp_path / ".continue").mkdir()
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "continue" for a in detected)

        # Create Zed settings folder
        (tmp_path / ".zed").mkdir()
        detected = detect_installed_agents(tmp_path)
        assert any(a.id == "zed" for a in detected)


def test_agent_detection_binary_path(tmp_path: Path) -> None:
    """Test detection via system PATH executables."""

    def fake_which(cmd: str) -> str | None:
        if cmd in ("cursor", "aider", "zed"):
            return f"/usr/local/bin/{cmd}"
        return None

    with patch("shutil.which", side_effect=fake_which):
        detected = detect_installed_agents(tmp_path)
        detected_ids = {a.id for a in detected}
        assert "cursor" in detected_ids
        assert "aider" in detected_ids
        assert "zed" in detected_ids
        assert "cline" not in detected_ids


def test_idempotent_sentinel_replacement_markdown(tmp_path: Path) -> None:
    """Test non-destructive sentinel injection and upgrade in Markdown files."""
    test_files = [
        "CLAUDE.md",
        "AGENTS.md",
        ".github/copilot-instructions.md",
        ".windsurfrules",
        ".clinerules",
    ]

    human_header = "# Team Handbook\n\nRule: Always verify with tests before pushing.\n"
    human_footer = "\n## Appendix\n\nContact infra@example.com for keys.\n"

    for rel_path in test_files:
        file_path = tmp_path / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Legacy sentinel block
        initial_content = (
            f"{human_header}\n"
            f"<!-- SYNAP_MANAGED_START: v1.0 -->\n"
            f"# Outdated Directives\n"
            f"Old body\n"
            f"<!-- SYNAP_MANAGED_END -->\n"
            f"{human_footer}"
        )
        file_path.write_text(initial_content, encoding="utf-8")

        # First install
        install_skills(tmp_path, targets=[rel_path])
        content_1 = file_path.read_text(encoding="utf-8")

        # Verify human text strictly preserved
        assert human_header.strip() in content_1
        assert human_footer.strip() in content_1
        # Verify old body replaced
        assert "Old body" not in content_1
        # Verify v3.0 sentinel block present
        assert SYNAP_START_MARKER in content_1
        assert SYNAP_END_MARKER in content_1
        assert "<!-- SYNAP_MANAGED_START: v3.0 -->" in content_1
        assert content_1.count(SYNAP_START_MARKER) == 1
        assert content_1.count(SYNAP_END_MARKER) == 1

        # Second install (idempotency check)
        install_skills(tmp_path, targets=[rel_path])
        content_2 = file_path.read_text(encoding="utf-8")
        assert content_2 == content_1


def test_idempotent_sentinel_yaml_aider(tmp_path: Path) -> None:
    """Test non-destructive sentinel injection into Aider YAML config."""
    aider_path = tmp_path / ".aider.conf.yml"
    user_yaml = "model: claude-3-5-sonnet\nedit-format: diff\nauto-commits: false\n"
    aider_path.write_text(user_yaml, encoding="utf-8")

    install_skills(tmp_path, targets=[".aider.conf.yml"])
    content_1 = aider_path.read_text(encoding="utf-8")

    # User YAML preserved
    assert "model: claude-3-5-sonnet" in content_1
    assert "edit-format: diff" in content_1
    assert "auto-commits: false" in content_1

    # Sentinel present
    assert SYNAP_START_MARKER in content_1
    assert SYNAP_END_MARKER in content_1

    # Second install produces identical result
    install_skills(tmp_path, targets=[".aider.conf.yml"])
    content_2 = aider_path.read_text(encoding="utf-8")
    assert content_2 == content_1


def test_idempotent_sentinel_json_continue_and_zed(tmp_path: Path) -> None:
    """Test non-destructive sentinel injection into JSON configs."""
    continue_path = tmp_path / ".continue/config.json"
    continue_path.parent.mkdir(parents=True, exist_ok=True)
    initial_continue = {
        "models": [{"title": "Claude 3.5", "model": "claude-3-5-sonnet"}],
        "customCommands": [{"name": "test", "prompt": "run pytest"}],
    }
    continue_path.write_text(json.dumps(initial_continue, indent=2), encoding="utf-8")

    install_skills(tmp_path, targets=[".continue/config.json"])
    data_1 = json.loads(continue_path.read_text(encoding="utf-8"))

    # Original keys preserved
    assert data_1["models"] == initial_continue["models"]
    assert data_1["customCommands"] == initial_continue["customCommands"]
    assert SYNAP_START_MARKER in data_1
    assert data_1[SYNAP_END_MARKER] is True

    # Second install produces identical result
    install_skills(tmp_path, targets=[".continue/config.json"])
    data_2 = json.loads(continue_path.read_text(encoding="utf-8"))
    assert data_2 == data_1

    # Test Zed settings.json
    zed_path = tmp_path / ".zed/settings.json"
    zed_path.parent.mkdir(parents=True, exist_ok=True)
    initial_zed = {
        "theme": "One Dark",
        "buffer_font_size": 14,
    }
    zed_path.write_text(json.dumps(initial_zed, indent=2), encoding="utf-8")

    install_skills(tmp_path, targets=[".zed/settings.json"])
    zed_data_1 = json.loads(zed_path.read_text(encoding="utf-8"))
    assert zed_data_1["theme"] == "One Dark"
    assert zed_data_1["buffer_font_size"] == 14
    assert SYNAP_START_MARKER in zed_data_1
    assert zed_data_1[SYNAP_END_MARKER] is True

    # Idempotent second run
    install_skills(tmp_path, targets=[".zed/settings.json"])
    zed_data_2 = json.loads(zed_path.read_text(encoding="utf-8"))
    assert zed_data_2 == zed_data_1


def test_skill_md_token_budget_under_600() -> None:
    """Ensure SKILL.md is strictly under 600 tokens using tiktoken o200k_base."""
    enc = tiktoken.get_encoding("o200k_base")
    skill_content = get_skill_template()

    tokens = enc.encode(skill_content)
    token_count = len(tokens)
    assert token_count < 600, f"SKILL.md token count {token_count} exceeds 600 limit!"

    # Ensure 3-step loop is cleanly represented
    assert "When to Fetch Context" in skill_content or "Fetch Context Before Work" in skill_content
    assert "Search Before Grepping" in skill_content
    assert "When to Write Memory" in skill_content or "Remember After Decisions" in skill_content

    # Ensure grounded benchmark numbers are present
    assert "85.2%" in skill_content
    assert "14ms" in skill_content
    assert "84ms" in skill_content
    assert "2.1ms" in skill_content


def test_benchmark_numbers_grounded() -> None:
    """Verify numbers in bench/numbers.json match ground truth schema and data."""
    numbers_path = Path(__file__).resolve().parent.parent / "bench" / "numbers.json"
    assert numbers_path.exists(), "bench/numbers.json does not exist!"

    data = json.loads(numbers_path.read_text(encoding="utf-8"))
    assert data["tokenizer"] == "o200k_base"
    assert "metrics_overall" in data
    assert "budget_evaluation" in data
    assert data["metrics_overall"]["recall_at_5"] > 0
    assert data["metrics_overall"]["mrr"] > 0

    # Check README.md contains matching numbers
    readme_path = Path(__file__).resolve().parent.parent / "README.md"
    readme_content = readme_path.read_text(encoding="utf-8")
    assert "bench/numbers.json" in readme_content
    assert "85.2%" in readme_content
