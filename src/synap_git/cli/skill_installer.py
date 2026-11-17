"""Idempotent installer for Synapse skills, agent directives, and IDE configs.

Installs and updates agent configurations across supported platforms:
- Claude Code (.claude/skills/synap/SKILL.md, CLAUDE.md)
- Cursor (.cursor/rules/synap.mdc)
- Codex CLI (AGENTS.md)
- Gemini CLI (AGENTS.md, .gemini/config/skills/synap/SKILL.md)
- GitHub Copilot (.github/copilot-instructions.md)
- Windsurf (.windsurfrules)
- Cline / Roo Code (.clinerules)
- Aider (.aider.conf.yml)
- Continue (.continue/config.json)
- Zed (.zed/settings.json)

Guarantees non-destructive updates: human-written instructions outside the
sentinel block are strictly preserved.
"""

from __future__ import annotations

import importlib.resources as pkg_resources
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import structlog

logger = structlog.get_logger()

SYNAP_START_MARKER: Final[str] = "<!-- SYNAP_MANAGED_START: v3.0 -->"
SYNAP_END_MARKER: Final[str] = "<!-- SYNAP_MANAGED_END -->"

SENTINEL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:#\s*)?<!--\s*SYNAP_MANAGED_START(?::\s*[^>]+)?\s*-->.*?(?:#\s*)?<!--\s*SYNAP_MANAGED_END\s*-->",
    re.DOTALL,
)

SYNAPSE_DIRECTIVES_BODY: Final[str] = """# Synapse AI Agent Directives

This project uses Synapse for persistent structural context, graph navigation, and memory.
Follow this 3-step operational loop:

## 1. When to Fetch Context (Before Work)
- Call `get_session_preamble()` at the start of every session or task to load active branch state, latest checkpoint, and approved negative constraints (revert lessons).
- Use `synap context` (or `get_session_preamble()`) to establish repo orientation within a bounded < 750 token budget.
- Never start modifying code before inspecting blast radius and active negative constraints.

## 2. Search Before Grepping
- Query symbols with `search(query="...", summary_only=True)` before performing raw greps across large files.
- Inspect structure with `get_skeleton(file_path="...")` to view typed signatures and docstrings without function bodies (85% token reduction).
- Read exact symbol implementations with `read_symbol(symbol="...", file_path="...")` instead of loading entire files.
- Check call chains with `get_callers(symbol="...")` or `get_neighborhood(symbol="...", direction="upstream")` before refactoring.

## 3. When to Write Memory (After Decisions & Fixes)
- Call `create_checkpoint(doing="...", next_step="...")` before context compaction, task handoffs, or complex edits.
- Record architectural choices with `log_decision(content="...", context_info="...")` to persist structural rationale.
- Store runtime discoveries and environment facts with `remember(key="...", content="...")` and lookup with `recall(key="...")`.
- Never repeat failures recorded in negative constraints. Never store secrets, passwords, or raw logs."""

MANAGED_BLOCK: Final[str] = f"{SYNAP_START_MARKER}\n{SYNAPSE_DIRECTIVES_BODY}\n{SYNAP_END_MARKER}"

YAML_MANAGED_BLOCK: Final[str] = f"""# {SYNAP_START_MARKER}
# Synapse AI Agent Directives
# 1. Fetch context before work: run `synap context` or call get_session_preamble()
# 2. Search before grepping: run `synap search <query>` or call get_skeleton()
# 3. Remember after decisions: run `synap remember <key> <val>` or call create_checkpoint()
# {SYNAP_END_MARKER}"""

CURSOR_MDC_HEADER: Final[str] = """---
description: Synapse AI Agent Directives for persistent context and graph navigation
globs: *
alwaysApply: true
---
"""


@dataclass(frozen=True)
class AgentDefinition:
    """Specification of a supported AI agent and its configuration paths."""

    id: str
    name: str
    config_paths: tuple[str, ...]
    status: str  # "tested end-to-end" or "generated, untested"
    detection_indicators: tuple[str, ...]
    format_type: str  # "markdown", "skill", "mdc", "yaml", "json", "mixed"


SUPPORTED_AGENTS: Final[list[AgentDefinition]] = [
    AgentDefinition(
        id="claude",
        name="Claude Code",
        config_paths=(".claude/skills/synap/SKILL.md", "CLAUDE.md"),
        status="tested end-to-end",
        detection_indicators=(".claude", "CLAUDE.md", "claude"),
        format_type="mixed",
    ),
    AgentDefinition(
        id="cursor",
        name="Cursor",
        config_paths=(".cursor/rules/synap.mdc",),
        status="tested end-to-end",
        detection_indicators=(".cursor", ".cursorrules", "cursor"),
        format_type="mdc",
    ),
    AgentDefinition(
        id="codex",
        name="Codex CLI",
        config_paths=("AGENTS.md",),
        status="tested end-to-end",
        detection_indicators=("AGENTS.md", ".codex", "codex"),
        format_type="markdown",
    ),
    AgentDefinition(
        id="gemini",
        name="Gemini CLI",
        config_paths=("AGENTS.md", ".gemini/config/skills/synap/SKILL.md"),
        status="tested end-to-end",
        detection_indicators=(".gemini", "gemini"),
        format_type="mixed",
    ),
    AgentDefinition(
        id="copilot",
        name="GitHub Copilot",
        config_paths=(".github/copilot-instructions.md",),
        status="tested end-to-end",
        detection_indicators=(".github/copilot-instructions.md", ".github"),
        format_type="markdown",
    ),
    AgentDefinition(
        id="windsurf",
        name="Windsurf",
        config_paths=(".windsurfrules",),
        status="tested end-to-end",
        detection_indicators=(".windsurfrules", ".codeium", "windsurf"),
        format_type="markdown",
    ),
    AgentDefinition(
        id="cline",
        name="Cline / Roo Code",
        config_paths=(".clinerules",),
        status="tested end-to-end",
        detection_indicators=(".clinerules", ".roomodes", ".roo"),
        format_type="markdown",
    ),
    AgentDefinition(
        id="aider",
        name="Aider",
        config_paths=(".aider.conf.yml",),
        status="generated, untested",
        detection_indicators=(".aider.conf.yml", ".aider.tags.cache.v3", "aider"),
        format_type="yaml",
    ),
    AgentDefinition(
        id="continue",
        name="Continue",
        config_paths=(".continue/config.json",),
        status="generated, untested",
        detection_indicators=(".continue",),
        format_type="json",
    ),
    AgentDefinition(
        id="zed",
        name="Zed",
        config_paths=(".zed/settings.json",),
        status="generated, untested",
        detection_indicators=(".zed", "zed"),
        format_type="json",
    ),
]

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
    "codex": "AGENTS.md",
    "cursor": ".cursor/rules/synap.mdc",
    "cursor_mdc": ".cursor/rules/synap.mdc",
    ".cursor/rules/synap.mdc": ".cursor/rules/synap.mdc",
    "synap.mdc": ".cursor/rules/synap.mdc",
    "cursorrules": ".cursorrules",
    ".cursorrules": ".cursorrules",
    "copilot": ".github/copilot-instructions.md",
    "github_copilot": ".github/copilot-instructions.md",
    "copilot-instructions": ".github/copilot-instructions.md",
    ".github/copilot-instructions.md": ".github/copilot-instructions.md",
    "windsurf": ".windsurfrules",
    "windsurfrules": ".windsurfrules",
    ".windsurfrules": ".windsurfrules",
    "cline": ".clinerules",
    "roo": ".clinerules",
    "clinerules": ".clinerules",
    ".clinerules": ".clinerules",
    "aider": ".aider.conf.yml",
    "aider.conf.yml": ".aider.conf.yml",
    ".aider.conf.yml": ".aider.conf.yml",
    "continue": ".continue/config.json",
    ".continue/config.json": ".continue/config.json",
    "zed": ".zed/settings.json",
    ".zed/settings.json": ".zed/settings.json",
    "gemini": ".gemini/config/skills/synap/SKILL.md",
    "gemini_skill": ".gemini/config/skills/synap/SKILL.md",
    ".gemini/config/skills/synap/skill.md": ".gemini/config/skills/synap/SKILL.md",
}


def get_compatibility_matrix() -> list[dict[str, Any]]:
    """Return the agent compatibility matrix with exact config paths and verification status."""
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "config_paths": list(agent.config_paths),
            "status": agent.status,
            "format_type": agent.format_type,
            "detection_indicators": list(agent.detection_indicators),
        }
        for agent in SUPPORTED_AGENTS
    ]


def detect_installed_agents(repo_root: Path | None = None) -> list[AgentDefinition]:
    """Detect which supported AI agents are installed or configured in the environment.

    Checks:
    1. Presence of config files or indicator directories in `repo_root`.
    2. Presence of CLI binaries in the system PATH.
    """
    root = (repo_root or Path.cwd()).resolve()
    detected: list[AgentDefinition] = []

    for agent in SUPPORTED_AGENTS:
        is_present = False
        for indicator in agent.detection_indicators:
            # Check repo filesystem
            target = root / indicator
            if target.exists():
                is_present = True
                break
            # Check system PATH for binary
            if shutil.which(indicator):
                is_present = True
                break
        if is_present:
            detected.append(agent)

    return detected


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
    """Install or idempotently update a Markdown or MDC directive file."""
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


def _install_yaml_directive_file(target_path: Path) -> None:
    """Install or idempotently update a YAML configuration file (e.g. .aider.conf.yml)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if not target_path.exists():
        target_path.write_text(f"{YAML_MANAGED_BLOCK}\n", encoding="utf-8")
        return

    existing = target_path.read_text(encoding="utf-8")
    new_content = inject_managed_block(existing, YAML_MANAGED_BLOCK)
    if new_content != existing:
        target_path.write_text(new_content, encoding="utf-8")


def _install_json_directive_file(target_path: Path) -> None:
    """Install or idempotently update a JSON configuration file (e.g. .continue/config.json, .zed/settings.json)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    managed_dict = {
        SYNAP_START_MARKER: {
            "description": "Synapse structural context engine directives",
            "directives": [
                "1. Fetch context before work (synap context / get_session_preamble)",
                "2. Search before grepping (synap search / get_skeleton)",
                "3. Remember after decisions (synap remember / create_checkpoint)",
            ],
        },
        SYNAP_END_MARKER: True,
    }

    if not target_path.exists():
        target_path.write_text(f"{json.dumps(managed_dict, indent=2)}\n", encoding="utf-8")
        return

    existing = target_path.read_text(encoding="utf-8")

    # Try JSON parse and merge first (guarantees valid JSON structure and idempotency)
    try:
        data = json.loads(existing)
        if isinstance(data, dict):
            data[SYNAP_START_MARKER] = managed_dict[SYNAP_START_MARKER]
            data[SYNAP_END_MARKER] = True
            target_path.write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")
            return
    except Exception:
        pass

    # Fallback to sentinel block replacement if JSON parsing fails
    match = SENTINEL_PATTERN.search(existing)
    if match:
        before = existing[: match.start()]
        after = existing[match.end() :]
        target_path.write_text(f"{before}{MANAGED_BLOCK}{after}", encoding="utf-8")
        return

    new_content = inject_managed_block(existing, MANAGED_BLOCK)
    target_path.write_text(new_content, encoding="utf-8")


def _install_skill_file(target_path: Path) -> None:
    """Install or update SKILL.md template file."""
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
        elif low in ("all_agents", "all-agents", "all_supported", "all-supported"):
            for agent in SUPPORTED_AGENTS:
                for cp in agent.config_paths:
                    if cp not in resolved:
                        resolved.append(cp)
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
        targets: Optional list of target names or relative paths. Defaults to standard targets:
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
        elif rel_path.endswith((".yml", ".yaml")):
            _install_yaml_directive_file(file_path)
        elif rel_path.endswith(".json"):
            _install_json_directive_file(file_path)
        else:
            _install_directive_file(file_path, is_cursor_mdc=False)
        installed.append(rel_path)
        logger.debug("synapse_skill_installed", path=str(file_path))

    return installed


def install_detected_agents(repo_root: Path) -> list[str]:
    """Detect installed agents in repo or environment and install their configs."""
    detected = detect_installed_agents(repo_root)
    targets: list[str] = []
    for agent in detected:
        for path in agent.config_paths:
            if path not in targets:
                targets.append(path)
    return install_skills(repo_root, targets=targets)
