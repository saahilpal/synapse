from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from synap_git.cli.main import app
from synap_git.cli.registry import (
    COMMAND_REGISTRY,
    generate_help_markdown,
    generate_skill_commands_markdown,
    generate_tui_slash_commands,
    get_all_commands,
    get_command,
    get_core_agent_commands,
)
from synap_git.cli.selftest import run_agent_selftest
from synap_git.cli.stats import (
    DEFAULT_ESTIMATION_METHOD,
    get_stats_path,
    load_stats,
    record_usage,
)
from synap_git.cli.tui import SLASH_COMMANDS, SynapInteractiveREPL


def _parse_json(output: str) -> dict[str, Any]:
    lines = output.strip().splitlines()
    for i in range(len(lines)):
        try:
            res = json.loads("\n".join(lines[i:]))
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    fallback = json.loads(output)
    if isinstance(fallback, dict):
        return fallback
    return {}


def test_core_agent_commands_registered() -> None:
    """Verify that all 10 core agent commands are registered and marked is_core_agent."""
    expected_core = {
        "ctx",
        "find",
        "remember",
        "status",
        "mcp",
        "bench",
        "stats",
        "init",
        "doctor",
        "selftest",
    }
    core_commands = get_core_agent_commands()
    core_names = {c.name for c in core_commands}

    assert expected_core.issubset(core_names), (
        f"Missing core commands: {expected_core - core_names}"
    )

    for name in expected_core:
        cmd = get_command(name)
        assert cmd is not None, f"Command '{name}' not found in registry"
        assert cmd.is_core_agent is True, f"Command '{name}' must have is_core_agent=True"
        assert cmd.one_line_help, f"Command '{name}' must have one_line_help"
        assert cmd.description, f"Command '{name}' must have description"
        assert cmd.examples, f"Command '{name}' must have examples"


def test_every_registry_command_is_executable() -> None:
    """Verify that every single command defined in the registry is registered in Typer app

    and executes '--help' successfully with exit code 0.
    """
    runner = CliRunner()
    all_cmds = get_all_commands()
    assert len(all_cmds) >= 30, f"Expected at least 30 commands, got {len(all_cmds)}"

    failed_commands: list[tuple[str, str]] = []
    for cmd in all_cmds:
        res = runner.invoke(app, [cmd.name, "--help"])
        if res.exit_code != 0:
            failed_commands.append((cmd.name, res.output))

    assert not failed_commands, f"Commands failed --help execution: {failed_commands}"


def test_aliases_are_executable() -> None:
    """Verify that shorthand command aliases (sk, ex, t, doc, search) execute cleanly."""
    runner = CliRunner()
    aliases = ["sk", "ex", "t", "doc", "search"]
    for alias in aliases:
        res = runner.invoke(app, [alias, "--help"])
        assert res.exit_code == 0, f"Alias '{alias}' failed --help: {res.output}"


def test_no_unregistered_commands_in_documentation() -> None:
    """Verify that no documentation or guide mentions an unregistered synap CLI command."""
    doc_paths = [
        Path("README.md"),
        Path("src/synap_git/resources/SKILL.md"),
        Path("DECISIONS.md"),
        Path("AGENTS.md"),
    ]

    cmd_pattern = re.compile(r"\bsynap\s+([a-zA-Z0-9_-]+)")
    unregistered: list[tuple[str, str]] = []

    for path in doc_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for line_num, line in enumerate(text.splitlines(), start=1):
            # Only match actual CLI commands, not yaml properties or comments
            for match in cmd_pattern.finditer(line):
                subcmd = match.group(1).strip()
                # Skip options/flags like --help, -v, etc.
                if subcmd.startswith("-"):
                    continue
                # Skip non-command words
                if subcmd not in COMMAND_REGISTRY:
                    unregistered.append((f"{path}:{line_num}", subcmd))

    assert not unregistered, f"Found unregistered commands in documentation: {unregistered}"


def test_stats_local_tracking_and_estimation_method(tmp_path: Path) -> None:
    """Verify that synap stats tracks cumulative usage locally in .synap/stats.json

    with zero telemetry and explicit estimation method labeling.
    """
    repo = tmp_path / "stats_repo"
    repo.mkdir()

    # 1. Initial state
    stats = load_stats(repo)
    assert stats["calls"] == 0
    assert stats["tokens_served"] == 0
    assert stats["estimated_tokens_avoided"] == 0
    assert stats["estimation_method"] == DEFAULT_ESTIMATION_METHOD

    # 2. Record usage across operations
    record_usage(repo, "ctx", tokens_served=300, estimated_tokens_avoided=2100)
    record_usage(repo, "skeleton", tokens_served=150, estimated_tokens_avoided=975)
    record_usage(repo, "find", tokens_served=200, estimated_tokens_avoided=1600)

    updated = load_stats(repo)
    assert updated["calls"] == 3
    assert updated["tokens_served"] == 650
    assert updated["estimated_tokens_avoided"] == 4675
    assert "ctx" in updated["breakdown"]
    assert "skeleton" in updated["breakdown"]
    assert "find" in updated["breakdown"]

    # Verify physical file existence
    stats_file = get_stats_path(repo)
    assert stats_file.exists()

    # 3. Test CLI command output
    runner = CliRunner()
    res = runner.invoke(app, ["stats", "--path", repo.as_posix()])
    assert res.exit_code == 0
    assert "Synapse Local Token Efficiency (No Telemetry)" in res.output
    assert "650" in res.output
    assert "Methodology Note" in res.output

    # 4. Test JSON output
    res_json = runner.invoke(app, ["stats", "--path", repo.as_posix(), "--json"])
    assert res_json.exit_code == 0
    data = _parse_json(res_json.output)
    assert data["calls"] == 3
    assert data["tokens_served"] == 650

    # 5. Test stats reset
    res_reset = runner.invoke(app, ["stats", "--path", repo.as_posix(), "--reset"])
    assert res_reset.exit_code == 0
    reset_stats = load_stats(repo)
    assert reset_stats["calls"] == 0
    assert reset_stats["tokens_served"] == 0


def test_agent_selftest_workflow() -> None:
    """Verify that synap selftest --agent simulates the entire SKILL.md workflow end-to-end."""
    # 1. Direct programmatic execution
    result = run_agent_selftest(verbose=False)
    assert result["success"] is True
    assert len(result["stages"]) >= 6

    stage_names = [s["stage"] for s in result["stages"]]
    assert "0_initialize_and_index" in stage_names
    assert "1_startup_preamble" in stage_names
    assert "2_context_fetch_ctx" in stage_names
    assert "3_remember_decision" in stage_names
    assert "4_query_symbols" in stage_names
    assert "5_read_skeleton" in stage_names
    assert "6_token_stats_tracking" in stage_names

    for s in result["stages"]:
        assert s["passed"] is True, f"Stage {s['stage']} failed: {s.get('message')}"

    # 2. CLI runner invocation
    runner = CliRunner()
    cli_res = runner.invoke(app, ["selftest", "--agent"])
    assert cli_res.exit_code == 0
    assert "All SKILL.md agent self-test stages passed successfully" in cli_res.output


def test_tui_and_registry_zero_drift(tmp_path: Path) -> None:
    """Verify that TUI slash commands and help tables stay 100% in sync with the registry."""
    # 1. Autocompletion list equals generate_tui_slash_commands()
    assert SLASH_COMMANDS == generate_tui_slash_commands()
    assert len(SLASH_COMMANDS) >= 15

    slash_names = [cmd for cmd, _ in SLASH_COMMANDS]
    for required in [
        "/init",
        "/status",
        "/find",
        "/remember",
        "/forget",
        "/ctx",
        "/stats",
        "/selftest",
        "/help",
        "/quit",
    ]:
        assert required in slash_names, f"Required slash command {required} not in TUI commands"

    # 2. REPL execution and /memory deprecation handling
    repl = SynapInteractiveREPL(repo_path=tmp_path)
    assert repl.execute_command("/help") is True

    # Test /memory deprecation warning & guidance
    assert repl.execute_command("/memory remember test_key test_val") is True
    # Test /remember and /forget
    assert repl.execute_command("/remember auth_rule Always check token expiry") is True
    assert repl.execute_command("/forget auth_rule") is True


def test_markdown_generators() -> None:
    """Verify that helper functions generate compliant markdown documentation."""
    help_md = generate_help_markdown()
    assert "## Command Reference" in help_md
    assert "### Core Agent Commands" in help_md
    assert "| `ctx` |" in help_md
    assert "| `find` |" in help_md
    assert "| `remember` |" in help_md
    assert "| `stats` |" in help_md

    skill_md = generate_skill_commands_markdown()
    assert "### Essential Synapse Commands" in skill_md
    assert "`synap ctx" in skill_md
    assert "`synap find" in skill_md
    assert "`synap skeleton" in skill_md
    assert "`synap remember" in skill_md
    assert "`synap stats`" in skill_md
