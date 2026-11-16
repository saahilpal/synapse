"""Idempotent installer for Synapse skills and agent directives.

Installs and updates:
- .claude/skills/synap/SKILL.md
- CLAUDE.md (bounded sentinel markers)
- AGENTS.md (bounded sentinel markers)
- .cursor/rules/synap.mdc (bounded sentinel markers)

Guarantees non-destructive updates: human-written instructions outside the
sentinel block are strictly preserved.
"""

from __future__ import annotations

import importlib.resources as pkg_resources
import re
from pathlib import Path
from typing import Final

import structlog

logger = structlog.get_logger()

SYNAP_START_MARKER: Final[str] = "<!-- SYNAP_MANAGED_START: v1.0 -->"
SYNAP_END_MARKER: Final[str] = "<!-- SYNAP_MANAGED_END -->"

SENTINEL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*SYNAP_MANAGED_START(?::\s*[^>]+)?\s*-->.*?<!--\s*SYNAP_MANAGED_END\s*-->",
    re.DOTALL,
)

SYNAPSE_DIRECTIVES_BODY: Final[str] = """# Synapse AI Agent Directives

This project uses Synapse for persistent structural context, graph navigation, and memory.
Follow these operational guidelines:

## 1. Session Start & Context Loading
- At the start of any conversation or task, call the MCP tool `get_session_preamble()`.
- Review the active branch, latest checkpoint, and approved negative constraints (lessons).
- If resuming an existing task, call `restore_checkpoint()`.
- Never repeat failures listed in approved lessons.

## 2. Progressive Code Navigation & Search
- When exploring, call `search(query="...", summary_only=True)` first to find relevant symbols with minimal token overhead.
- Use `get_skeleton(file_path="...")` to inspect function signatures, docstrings, and classes without implementation bodies (85% token savings).
- Use `get_outline(file_path="...")` to inspect file structure and line ranges.
- Use `read_symbol(symbol="...", file_path="...")` to read exact symbol code without reading entire files.
- Before modifying a symbol, use `get_callers(symbol="...")` or `get_neighborhood(symbol="...", direction="upstream")` to check caller blast radius.

## 3. Verification & Testing
- Use `get_diff()` to review uncommitted code changes.
- Use `get_test_recommendations()` to identify impacted test files and receive recommended pytest commands.

## 4. Session Checkpointing & Memory
- Before ending a complex task or when context is high, call `create_checkpoint(doing="...", next_step="...")`.
- Log key architectural decisions using `log_decision(content="...", context_info="...")`.
- Save critical environment facts or non-code observations using `remember(key="...", content="...")`, and look up with `recall(key="...")`."""

MANAGED_BLOCK: Final[str] = f"{SYNAP_START_MARKER}\n{SYNAPSE_DIRECTIVES_BODY}\n{SYNAP_END_MARKER}"

CURSOR_MDC_HEADER: Final[str] = """---
description: Synapse AI Agent Directives for persistent context and graph navigation
globs: *
alwaysApply: true
---
"""

DEFAULT_TARGETS: Final[list[str]] = [
    ".claude/skills/synap/SKILL.md",
    "CLAUDE.md",
    "AGENTS.md",
    ".cursor/rules/synap.mdc",
]

TARGET_ALIASES: Final[dict[str, str]] = {
    "skill": ".claude/skills/synap/SKILL.md",
    "skills": ".claude/skills/synap/SKILL.md",
    "claude_skill": ".claude/skills/synap/SKILL.md",
    "claude-skill": ".claude/skills/synap/SKILL.md",
    ".claude/skills/synap/skill.md": ".claude/skills/synap/SKILL.md",
    "claude": "CLAUDE.md",
    "claude_md": "CLAUDE.md",
    "claude.md": "CLAUDE.md",
    "agents": "AGENTS.md",
    "agents_md": "AGENTS.md",
    "agents.md": "AGENTS.md",
    "cursor": ".cursor/rules/synap.mdc",
    "cursor_mdc": ".cursor/rules/synap.mdc",
    ".cursor/rules/synap.mdc": ".cursor/rules/synap.mdc",
    "synap.mdc": ".cursor/rules/synap.mdc",
    "cursorrules": ".cursorrules",
    ".cursorrules": ".cursorrules",
}


def get_skill_template() -> str:
    """Retrieve canonical SKILL.md template from package resources."""
    try:
        ref = pkg_resources.files("synap_git.resources").joinpath("SKILL.md")
        return ref.read_text(encoding="utf-8")
    except Exception:
        fallback = Path(__file__).resolve().parent.parent / "resources" / "SKILL.md"
        if fallback.exists():
            return fallback.read_text(encoding="utf-8")
        raise FileNotFoundError("Could not locate SKILL.md resource template in package.")


def inject_managed_block(existing_content: str, managed_block: str) -> str:
    """Inject managed block into existing content while strictly preserving surrounding text.

    - Replaces existing sentinel block if present.
    - Upgrades legacy un-sentineled directives if present.
    - Otherwise appends managed block to existing content.
    """
    match = SENTINEL_PATTERN.search(existing_content)
    if match:
        before = existing_content[: match.start()]
        after = existing_content[match.end() :]
        return f"{before}{managed_block}{after}"

    # Legacy un-sentineled directive handling
    legacy_marker = "# Synapse AI Agent Directives"
    if legacy_marker in existing_content:
        idx = existing_content.find(legacy_marker)
        before = existing_content[:idx].rstrip()
        if before:
            return f"{before}\n\n{managed_block}\n"
        return f"{managed_block}\n"

    # Clean append preserving human instructions
    stripped = existing_content.rstrip()
    if stripped:
        return f"{stripped}\n\n{managed_block}\n"
    return f"{managed_block}\n"


def _install_directive_file(target_path: Path, is_cursor_mdc: bool = False) -> None:
    """Install or idempotently update a directive file."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if not target_path.exists():
        if is_cursor_mdc:
            content = f"{CURSOR_MDC_HEADER}\n{MANAGED_BLOCK}\n"
        else:
            content = f"{MANAGED_BLOCK}\n"
        target_path.write_text(content, encoding="utf-8")
        return

    existing = target_path.read_text(encoding="utf-8")
    new_content = inject_managed_block(existing, MANAGED_BLOCK)
    if new_content != existing:
        target_path.write_text(new_content, encoding="utf-8")


def _install_skill_file(target_path: Path) -> None:
    """Install or update .claude/skills/synap/SKILL.md."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    template = get_skill_template()
    if not target_path.exists() or target_path.read_text(encoding="utf-8") != template:
        target_path.write_text(template, encoding="utf-8")


def resolve_targets(targets: list[str] | None) -> list[str]:
    """Resolve user-supplied target identifiers into canonical relative paths."""
    if targets is None:
        return list(DEFAULT_TARGETS)

    resolved: list[str] = []
    for raw in targets:
        low = raw.strip().lower()
        if low == "all":
            for dt in DEFAULT_TARGETS:
                if dt not in resolved:
                    resolved.append(dt)
        elif low in TARGET_ALIASES:
            canonical = TARGET_ALIASES[low]
            if canonical not in resolved:
                resolved.append(canonical)
        elif raw.strip() in DEFAULT_TARGETS or raw.strip() in TARGET_ALIASES.values():
            canonical = raw.strip()
            if canonical not in resolved:
                resolved.append(canonical)
        else:
            # Custom path
            if raw.strip() not in resolved:
                resolved.append(raw.strip())
    return resolved


def install_skills(repo_root: Path, targets: list[str] | None = None) -> list[str]:
    """Idempotently install or update Synapse skill and directive files.

    Args:
        repo_root: Root path of the repository.
        targets: Optional list of target names or relative paths. Defaults to all standard targets:
            - .claude/skills/synap/SKILL.md
            - CLAUDE.md
            - AGENTS.md
            - .cursor/rules/synap.mdc

    Returns:
        List of relative paths that were processed/installed.
    """
    root = repo_root.resolve()
    target_list = resolve_targets(targets)
    installed: list[str] = []

    for rel_path in target_list:
        file_path = root / rel_path
        if rel_path.endswith("SKILL.md"):
            _install_skill_file(file_path)
        elif rel_path.endswith(".cursor/rules/synap.mdc"):
            _install_directive_file(file_path, is_cursor_mdc=True)
        else:
            _install_directive_file(file_path, is_cursor_mdc=False)
        installed.append(rel_path)
        logger.debug("synapse_skill_installed", path=str(file_path))

    return installed
