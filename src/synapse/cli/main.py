from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from synapse.config import LoggingMode, RuntimeMode, RuntimeProfile, SynapseSettings
from synapse.diagnostics.logging import configure_logging
from synapse.indexer.daemon import RuntimeDaemon
from synapse.indexer.engine import SynapseRuntime

app = typer.Typer(
    name="synapse",
    help="Deterministic Git-aware structural retrieval engine for AI coding agents.",
    no_args_is_help=True,
)

JSON_OPTION = typer.Option("--json", help="Emit machine-readable JSON.")


def _settings(
    path: str,
    *,
    profile: RuntimeProfile = RuntimeProfile.DEV,
    json_output: bool = False,
    mode: RuntimeMode = RuntimeMode.ACTIVE,
) -> SynapseSettings:
    settings = SynapseSettings(
        repository_path=Path(path),
        profile=profile,
        logging_mode=LoggingMode.JSON if json_output else LoggingMode.HUMAN,
        mode=mode,
    )
    configure_logging(settings)
    return settings


def _emit(value: Any, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(_jsonable(value), indent=2, sort_keys=True))
        return
    if isinstance(value, str):
        typer.echo(value)
        return
    for key, item in _jsonable(value).items():
        typer.echo(f"{key}: {item}")


def _jsonable(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump(mode="json"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime | date):
        return value.isoformat()
    if is_dataclass(value):
        return _jsonable(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return _jsonable(value.__dict__)
    return value


mcp_app = typer.Typer(help="Model Context Protocol (MCP) server commands.")
app.add_typer(mcp_app, name="mcp")

memory_app = typer.Typer(help="Manage L3 Agent Memory.")
app.add_typer(memory_app, name="memory")

lessons_app = typer.Typer(help="Manage Agent Lessons.")
app.add_typer(lessons_app, name="lessons")

checkpoint_app = typer.Typer(help="Manage Context Checkpoints.")
app.add_typer(checkpoint_app, name="checkpoint")

wiki_app = typer.Typer(help="Manage L2 Wiki Documentation.")
app.add_typer(wiki_app, name="wiki")

cost_app = typer.Typer(help="View AI Cost Tracking.")
app.add_typer(cost_app, name="cost")


@app.command()
def setup(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Interactive first-run setup and onboarding."""
    typer.secho("Welcome to Synapse AI Context Runtime", fg=typer.colors.CYAN, bold=True)
    typer.echo("This wizard will bootstrap your local AI environment.\n")

    config_dir = Path("~/.config/synapse").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"

    typer.secho("Synapse stores API keys securely in your system keyring.", fg=typer.colors.YELLOW)
    typer.echo(f"Global configuration: {config_file.as_posix()}\n")

    # 1. Choose Provider
    provider = typer.prompt(
        "Which primary LLM provider would you like to use?",
        default="ollama",
    ).lower()

    # 2. Configure LLM
    llm_model = typer.prompt(
        f"Which model would you like to use for {provider}?",
        default="qwen2.5-coder:14b" if provider == "ollama" else "gpt-4o",
    )

    # Gather Keys if needed
    ollama_url = "http://localhost:11434"

    import keyring

    if provider == "openai":
        key = typer.prompt("Enter OpenAI API Key", hide_input=True)
        keyring.set_password("synapse", "openai_api_key", key)
    elif provider == "gemini":
        key = typer.prompt("Enter Gemini API Key", hide_input=True)
        keyring.set_password("synapse", "gemini_api_key", key)
    elif provider == "anthropic":
        key = typer.prompt("Enter Anthropic API Key", hide_input=True)
        keyring.set_password("synapse", "anthropic_api_key", key)
    elif provider == "ollama":
        ollama_url = typer.prompt("Enter Ollama URL", default="http://localhost:11434")

    # Build TOML config (non-sensitive only)
    config_content = f"""[llm]
llm_provider = "{provider}"
llm_model = "{llm_model}"
ollama_url = "{ollama_url}"
"""
    config_file.write_text(config_content)
    typer.secho(f"\n✓ Configuration saved to {config_file.as_posix()}", fg=typer.colors.GREEN)
    typer.secho("✓ Secrets saved to system keyring.", fg=typer.colors.GREEN)

    # Initialize storage
    runtime = SynapseRuntime(_settings(path))
    runtime.bootstrap(force=True)
    typer.secho("✓ Storage initialized.", fg=typer.colors.GREEN)


@app.command()
def init(
    path: Annotated[str, typer.Argument(help="Repository path to initialize.")] = ".",
    force: Annotated[bool, typer.Option(help="Force reindexing.")] = False,
    skip_llm: Annotated[
        bool, typer.Option("--skip-llm", help="Run in Mode A (structural only).")
    ] = False,
    skip_wiki: Annotated[
        bool, typer.Option("--skip-wiki", help="Skip L2 documentation generation.")
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Suppress output.")] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Initialize local Synapse state and perform first scan."""
    settings = _settings(path, json_output=json_output)
    if skip_llm:
        settings.llm_provider = None

    runtime = SynapseRuntime(settings)
    commit = runtime.bootstrap(force=force)

    if json_output:
        _emit({"active_commit": commit, "state": "initialized"}, json_output=True)
    elif not quiet:
        typer.secho(f"✓ Initialized repository at {commit}", fg=typer.colors.GREEN)


@app.command()
def wipe(
    path: Annotated[str, typer.Argument(help="Repository path to wipe.")] = ".",
) -> None:
    """Completely purge the local index for a fresh rebuild."""
    if not typer.confirm("This will delete all indexed symbols and embeddings. Continue?"):
        raise typer.Abort()
    runtime = SynapseRuntime(_settings(path))
    runtime.wipe_index()
    typer.secho("✓ Index wiped.", fg=typer.colors.GREEN)


@app.command()
def start(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Start the simplified repository context daemon."""
    settings = _settings(path, json_output=json_output)
    daemon = RuntimeDaemon(settings)
    asyncio.run(daemon.start())


@app.command()
def status(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show current repository context status."""
    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.status(), json_output=json_output)


@app.command()
def rollback(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Rollback active state to a previous commit."""
    typer.secho("Rollback not implemented yet.", fg=typer.colors.YELLOW)


@app.command()
def recover(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Recover from a broken index state."""
    typer.secho("Recover not implemented yet.", fg=typer.colors.YELLOW)


@app.command()
def doctor(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    fix: Annotated[
        bool, typer.Option("--fix", help="Attempt to automatically fix detected issues.")
    ] = False,
    context: Annotated[
        bool, typer.Option("--context", help="Output current LLM injection context.")
    ] = False,
) -> None:
    """Validate environment and system health."""
    typer.secho("Synapse Doctor: System Health Check", fg=typer.colors.CYAN, bold=True)

    settings = _settings(path)
    runtime = SynapseRuntime(settings)

    # 1. Check SQLite
    try:
        runtime.initialize_storage()
        res = runtime.doctor()
        typer.secho(f"✓ Database integrity: {res['database_integrity']}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"✗ Database error: {e}", fg=typer.colors.RED)

    # 2. Check Parsers
    try:
        from synapse.parser.registry import CodeParserRegistry

        registry = CodeParserRegistry()
        # Test with a dummy python string
        test_file = Path(path) / ".synapse_test.py"
        test_file.write_text("def test(): pass")
        registry.parse(test_file, relative_path=".synapse_test.py")
        test_file.unlink()
        typer.secho("✓ Tree-sitter parsers functional", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"✗ Parser error: {e}", fg=typer.colors.RED)

    # 3. Check Tokenizer
    try:
        import tiktoken

        tiktoken.get_encoding("cl100k_base")
        typer.secho("✓ Tokenizer (tiktoken) ready", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"✗ Tokenizer error: {e}", fg=typer.colors.RED)

    # 4. Check Provider & Keyring
    try:
        errors = settings.validate_configuration()
        if errors:
            for err in errors:
                typer.secho(f"✗ Config error: {err}", fg=typer.colors.RED)
        else:
            typer.secho(f"✓ Provider configured: {settings.llm_provider}", fg=typer.colors.GREEN)
            typer.secho("✓ Keyring secrets accessible", fg=typer.colors.GREEN)

        conn_errors = settings.test_connectivity()
        if conn_errors:
            for err in conn_errors:
                typer.secho(f"✗ Connectivity error: {err}", fg=typer.colors.RED)
        else:
            typer.secho("✓ Provider connectivity verified", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"✗ Unexpected error: {e}", fg=typer.colors.RED)

    typer.echo("\nAll checks complete.")


@app.command()
def run(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
    host: Annotated[str, typer.Option(help="Host for UI server.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port for UI server.")] = 9876,
) -> None:
    """Start all Synapse services (Daemon, MCP, UI)."""
    import subprocess
    import sys
    import time

    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    commands = [
        ("Daemon", [sys.executable, "-m", "synapse.cli", "start", path]),
        ("MCP Server", [sys.executable, "-m", "synapse.cli", "mcp", "start", path]),
        (
            "UI Server",
            [sys.executable, "-m", "synapse.cli", "ui", path, "--host", host, "--port", str(port)],
        ),
    ]

    processes = []
    try:
        for name, cmd in commands:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
            processes.append((name, p))
            time.sleep(0.5)

        typer.secho("\n✓ Synapse Runtime active!", fg=typer.colors.GREEN, bold=True)
        typer.secho(f"UI: http://{host}:{port}", fg=typer.colors.CYAN)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for _, p in processes:
            p.terminate()


@mcp_app.command("start")
def mcp_start(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Start the MCP server."""
    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    from synapse.mcp.server import SynapseMCPServer

    server = SynapseMCPServer(runtime)
    asyncio.run(server.run())


@mcp_app.command("config")
def mcp_config(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Output the MCP server configuration for manual IDE setup."""
    abs_path = Path(path).resolve().as_posix()
    import sys

    config = {
        "mcpServers": {
            "synapse": {
                "command": sys.executable,
                "args": ["-m", "synapse.cli", "mcp", "start", abs_path],
                "autoConnect": True,
            }
        }
    }
    typer.echo(json.dumps(config, indent=2))


@app.command()
def ui(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 9876,
) -> None:
    """Start the diagnostic UI."""
    import uvicorn

    from synapse.api.app import create_app

    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    api_app = create_app(runtime)
    uvicorn.run(api_app, host=host, port=port)
