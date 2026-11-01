from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from synap_git import __version__
from synap_git.cli.main import app


def test_version_is_defined() -> None:
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_version_format_semver() -> None:
    # Version must follow Semantic Versioning (MAJOR.MINOR.PATCH[-PRERELEASE])
    pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$"
    assert re.match(pattern, __version__), f"Version '{__version__}' is not valid SemVer"


def test_package_exports() -> None:
    import synap_git

    assert hasattr(synap_git, "__all__")
    assert synap_git.__all__ == ["__version__"]
    assert synap_git.__version__ == __version__


def test_pyproject_metadata() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    pyproject_path = repo_root / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    assert project.get("name") == "synap-git"
    assert "version" in project.get("dynamic", [])

    scripts = project.get("scripts", {})
    assert scripts.get("synap") == "synap_git.cli:app"

    # Verify unused libraries (e.g. markdown-it-py) are not listed
    deps = project.get("dependencies", [])
    dep_names = [d.split("=")[0].split("<")[0].split(">")[0].strip() for d in deps]
    assert "markdown-it-py" not in dep_names, "markdown-it-py should be removed from dependencies"
    assert "typer" in dep_names
    assert "fastapi" in dep_names
    assert "pydantic" in dep_names


def test_cli_entrypoint_app_instance() -> None:
    assert isinstance(app, typer.Typer)


def test_cli_version_flags() -> None:
    runner = CliRunner()

    result_long = runner.invoke(app, ["--version"])
    assert result_long.exit_code == 0
    assert __version__ in result_long.output

    result_short = runner.invoke(app, ["-v"])
    assert result_short.exit_code == 0
    assert __version__ in result_short.output

    result_cmd = runner.invoke(app, ["version"])
    assert result_cmd.exit_code == 0
    assert __version__ in result_cmd.output


def test_cli_help() -> None:
    import re

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    clean = " ".join(re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output).split())
    assert "Usage: synap" in clean or "synap" in clean
    # Check core commands appear in help
    for cmd in ["init", "status", "start", "stop", "blast", "hubs", "search", "doctor", "mcp"]:
        assert cmd in clean


@pytest.mark.parametrize(
    "command_args",
    [
        ["init"],
        ["blast"],
        ["hubs"],
        ["index"],
        ["sync"],
        ["diff"],
        ["test"],
        ["context"],
        ["start"],
    ],
)
def test_non_git_directory_exits_cleanly(command_args: list[str], tmp_path: Path) -> None:
    runner = CliRunner()
    # Execute command pointing to or inside a non-git directory
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, command_args)
        assert result.exit_code == 1, (
            f"Expected code 1 for '{command_args}', got {result.exit_code}"
        )
        clean_output = " ".join(result.output.split())
        assert "is not a valid Git repository" in clean_output
        # Ensure no uncaught tracebacks
        assert "Traceback (most recent call last)" not in result.output


def test_non_git_directory_help_and_version(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        res_ver = runner.invoke(app, ["--version"])
        assert res_ver.exit_code == 0
        assert __version__ in res_ver.output

        res_help = runner.invoke(app, ["--help"])
        assert res_help.exit_code == 0
        clean_help = " ".join(re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", res_help.output).split())
        assert "Usage: synap" in clean_help or "synap" in clean_help
