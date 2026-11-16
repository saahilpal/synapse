"""Tests for Synapse skill and directive installer."""

from __future__ import annotations

from pathlib import Path

from synap_git.cli.skill_installer import (
    MANAGED_BLOCK,
    SYNAP_END_MARKER,
    SYNAP_START_MARKER,
    get_skill_template,
    inject_managed_block,
    install_skills,
)


def test_get_skill_template() -> None:
    template = get_skill_template()
    assert isinstance(template, str)
    assert len(template) > 0
    # Must have frontmatter name: synap
    assert "name: synap" in template
    # Must specify triggers: context fetching, memory writing, query phrasing, secrets
    assert "When to Fetch Context" in template
    assert "When to Write Memory" in template
    assert "What NEVER to Store" in template
    assert "secrets" in template.lower()


def test_fresh_creation(tmp_path: Path) -> None:
    installed = install_skills(tmp_path)
    assert len(installed) == 4
    assert ".claude/skills/synap/SKILL.md" in installed
    assert "CLAUDE.md" in installed
    assert "AGENTS.md" in installed
    assert ".cursor/rules/synap.mdc" in installed

    # Verify skill file
    skill_path = tmp_path / ".claude/skills/synap/SKILL.md"
    assert skill_path.exists()
    assert "name: synap" in skill_path.read_text(encoding="utf-8")

    # Verify CLAUDE.md
    claude_path = tmp_path / "CLAUDE.md"
    assert claude_path.exists()
    claude_content = claude_path.read_text(encoding="utf-8")
    assert SYNAP_START_MARKER in claude_content
    assert SYNAP_END_MARKER in claude_content
    assert "Synapse AI Agent Directives" in claude_content

    # Verify AGENTS.md
    agents_path = tmp_path / "AGENTS.md"
    assert agents_path.exists()
    agents_content = agents_path.read_text(encoding="utf-8")
    assert SYNAP_START_MARKER in agents_content
    assert SYNAP_END_MARKER in agents_content

    # Verify .cursor/rules/synap.mdc
    cursor_path = tmp_path / ".cursor/rules/synap.mdc"
    assert cursor_path.exists()
    cursor_content = cursor_path.read_text(encoding="utf-8")
    assert cursor_content.startswith("---")
    assert "description: Synapse AI Agent Directives" in cursor_content
    assert SYNAP_START_MARKER in cursor_content
    assert SYNAP_END_MARKER in cursor_content


def test_idempotency(tmp_path: Path) -> None:
    # First install
    install_skills(tmp_path)

    claude_path = tmp_path / "CLAUDE.md"
    agents_path = tmp_path / "AGENTS.md"
    cursor_path = tmp_path / ".cursor/rules/synap.mdc"
    skill_path = tmp_path / ".claude/skills/synap/SKILL.md"

    content_claude_1 = claude_path.read_text(encoding="utf-8")
    content_agents_1 = agents_path.read_text(encoding="utf-8")
    content_cursor_1 = cursor_path.read_text(encoding="utf-8")
    content_skill_1 = skill_path.read_text(encoding="utf-8")

    # Second install
    install_skills(tmp_path)

    assert claude_path.read_text(encoding="utf-8") == content_claude_1
    assert agents_path.read_text(encoding="utf-8") == content_agents_1
    assert cursor_path.read_text(encoding="utf-8") == content_cursor_1
    assert skill_path.read_text(encoding="utf-8") == content_skill_1

    # Third install
    install_skills(tmp_path)

    assert claude_path.read_text(encoding="utf-8") == content_claude_1
    # Check that sentinel appears exactly once
    assert content_claude_1.count(SYNAP_START_MARKER) == 1
    assert content_claude_1.count(SYNAP_END_MARKER) == 1
    assert content_cursor_1.count(SYNAP_START_MARKER) == 1
    assert content_cursor_1.count(SYNAP_END_MARKER) == 1


def test_non_destructive_preservation_existing_content(tmp_path: Path) -> None:
    human_prefix = "# Engineering Handbook\n\nRule 1: Always verify changes before pushing.\n"
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text(human_prefix, encoding="utf-8")

    install_skills(tmp_path, targets=["CLAUDE.md"])

    content = claude_path.read_text(encoding="utf-8")
    assert content.startswith(human_prefix.rstrip())
    assert SYNAP_START_MARKER in content
    assert SYNAP_END_MARKER in content


def test_non_destructive_block_replacement(tmp_path: Path) -> None:
    claude_path = tmp_path / "CLAUDE.md"
    initial_content = (
        "# Engineering Handbook\n\n"
        "Keep this human text safe.\n\n"
        "<!-- SYNAP_MANAGED_START: v0.9 -->\n"
        "# Outdated Directives\n"
        "Do old stuff.\n"
        "<!-- SYNAP_MANAGED_END -->\n\n"
        "## Human Appendices\n"
        "Never delete this footer!\n"
    )
    claude_path.write_text(initial_content, encoding="utf-8")

    install_skills(tmp_path, targets=["CLAUDE.md"])

    content = claude_path.read_text(encoding="utf-8")
    assert "# Engineering Handbook\n\nKeep this human text safe." in content
    assert "## Human Appendices\nNever delete this footer!" in content
    assert "Do old stuff." not in content
    assert SYNAP_START_MARKER in content
    assert SYNAP_END_MARKER in content
    assert "Synapse AI Agent Directives" in content


def test_legacy_unsentineled_directive_upgrade(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    legacy_content = (
        "# Custom Agent Rules\n"
        "Custom rule A.\n\n"
        "# Synapse AI Agent Directives\n"
        "Old un-sentineled body here.\n"
    )
    agents_path.write_text(legacy_content, encoding="utf-8")

    install_skills(tmp_path, targets=["AGENTS.md"])

    content = agents_path.read_text(encoding="utf-8")
    assert "# Custom Agent Rules\nCustom rule A." in content
    assert "Old un-sentineled body here." not in content
    assert SYNAP_START_MARKER in content
    assert SYNAP_END_MARKER in content
    # Should only have 1 directives heading
    assert content.count("# Synapse AI Agent Directives") == 1


def test_cursor_mdc_preserves_custom_frontmatter(tmp_path: Path) -> None:
    cursor_dir = tmp_path / ".cursor" / "rules"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    cursor_file = cursor_dir / "synap.mdc"

    custom_content = (
        "---\n"
        "description: Custom Developer Rule\n"
        "globs: *.ts\n"
        "---\n"
        "# My Team Rule\n"
        "Write typed code.\n"
    )
    cursor_file.write_text(custom_content, encoding="utf-8")

    install_skills(tmp_path, targets=["cursor"])

    result = cursor_file.read_text(encoding="utf-8")
    assert "description: Custom Developer Rule" in result
    assert "globs: *.ts" in result
    assert "# My Team Rule\nWrite typed code." in result
    assert SYNAP_START_MARKER in result
    assert SYNAP_END_MARKER in result

    # Test idempotency on custom MDC
    install_skills(tmp_path, targets=["cursor"])
    result_second = cursor_file.read_text(encoding="utf-8")
    assert result_second == result


def test_selective_targets(tmp_path: Path) -> None:
    installed = install_skills(tmp_path, targets=["claude", "cursor"])
    assert installed == ["CLAUDE.md", ".cursor/rules/synap.mdc"]

    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".cursor/rules/synap.mdc").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".claude/skills/synap/SKILL.md").exists()


def test_inject_managed_block_helper() -> None:
    # Empty string
    out = inject_managed_block("", MANAGED_BLOCK)
    assert out.strip() == MANAGED_BLOCK.strip()

    # Content with sentinel block
    original = f"Human Header\n\n{MANAGED_BLOCK}\n\nHuman Footer"
    new_managed = f"{SYNAP_START_MARKER}\nUpdated\n{SYNAP_END_MARKER}"
    updated = inject_managed_block(original, new_managed)
    assert "Human Header" in updated
    assert "Human Footer" in updated
    assert "Updated" in updated
    assert MANAGED_BLOCK not in updated
