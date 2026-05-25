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
from synapse.observability import configure_logging
from synapse.runtime.daemon import RuntimeDaemon
from synapse.runtime.service import SynapseRuntime

app = typer.Typer(
    name="synapse",
    help="Persistent structural context infrastructure for AI coding agents.",
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

    typer.secho("Synapse stores API keys securely in a global config file.", fg=typer.colors.YELLOW)
    typer.echo(f"Location: {config_file.as_posix()}\n")

    # 1. Choose Provider
    provider = typer.prompt(
        "Which primary LLM provider would you like to use?",
        default="ollama",
    ).lower()
    if provider not in ("ollama", "openai", "gemini", "anthropic"):
        typer.secho(f"Invalid provider: {provider}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # 2. Configure LLM
    llm_model = typer.prompt(
        f"Which model would you like to use for {provider}?",
        default="qwen2.5-coder:14b"
        if provider == "ollama"
        else "gpt-4o"
        if provider == "openai"
        else "claude-3-5-sonnet-latest"
        if provider == "anthropic"
        else "gemini-1.5-pro",
    )

    # 3. Configure Embeddings
    embed_provider = typer.prompt(
        "Which provider for embeddings?",
        default=provider,
    ).lower()
    if embed_provider not in ("ollama", "openai", "gemini", "anthropic"):
        typer.secho(f"Invalid provider: {embed_provider}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    embed_model = typer.prompt(
        "Which embedding model?",
        default="nomic-embed-text" if embed_provider == "ollama" else "text-embedding-3-small",
    )

    # Gather Keys if needed
    openai_key = ""
    gemini_key = ""
    anthropic_key = ""
    ollama_url = "http://localhost:11434"

    if provider == "openai" or embed_provider == "openai":
        openai_key = typer.prompt("Enter OpenAI API Key", hide_input=True, default="")
    if provider == "gemini" or embed_provider == "gemini":
        gemini_key = typer.prompt("Enter Gemini API Key", hide_input=True, default="")
    if provider == "anthropic" or embed_provider == "anthropic":
        anthropic_key = typer.prompt("Enter Anthropic API Key", hide_input=True, default="")
    if provider == "ollama" or embed_provider == "ollama":
        ollama_url = typer.prompt("Enter Ollama URL", default="http://localhost:11434")

    # Build TOML config (more secure format than .env)
    config_content = f"""# Synapse Global Configuration
# DO NOT commit this file to version control!
# This file contains sensitive API keys.

[llm]
provider = "{provider}"
model = "{llm_model}"

[embeddings]
provider = "{embed_provider}"
model = "{embed_model}"

[providers]
ollama_url = "{ollama_url}"
openai_api_key = "{openai_key}"
gemini_api_key = "{gemini_key}"
anthropic_api_key = "{anthropic_key}"
"""
    config_file.write_text(config_content)
    config_file.chmod(0o600)  # Restrict to owner only
    typer.secho(f"\n✓ Configuration saved to {config_file.as_posix()}", fg=typer.colors.GREEN)
    typer.secho("  (Permissions: 0600 - readable by you only)", fg=typer.colors.BRIGHT_BLACK)

    # Initialize storage
    typer.echo("\nInitializing storage...")
    runtime = SynapseRuntime(_settings(path))
    runtime.bootstrap(force=True)
    typer.secho("✓ Storage initialized.", fg=typer.colors.GREEN)

    typer.echo("\nYou are all set! Next steps:")
    typer.echo(f"  1. Start the runtime: synapse run {path}")
    typer.echo(f"  2. Open the UI: synapse ui {path}")
    typer.echo(
        f'  3. Try task-context: synapse task-context "describe authentication flow" {path}\n'
    )


@app.command()
def validate(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Validate Synapse configuration and provider connectivity."""
    settings = _settings(path, json_output=json_output)

    typer.secho("Validating Synapse configuration...\n", fg=typer.colors.CYAN, bold=True)

    # Check configuration completeness
    errors = settings.validate_configuration()
    if errors:
        typer.secho("Configuration errors found:", fg=typer.colors.RED, bold=True)
        for error in errors:
            typer.secho(f"  ✗ {error}", fg=typer.colors.RED)
        typer.echo(f"\nRun 'synapse setup {path}' to configure Synapse.")
        raise typer.Exit(code=1)

    typer.secho("✓ Configuration is valid.", fg=typer.colors.GREEN)
    typer.echo(f"  Config file: {settings.config_file_path().as_posix()}")
    typer.echo(f"  LLM: {settings.llm_provider}/{settings.llm_model}")
    typer.echo(f"  Embeddings: {settings.embed_provider or settings.llm_provider}")

    # Test provider connectivity
    typer.echo("\nTesting provider connectivity...")
    try:
        from synapse.provider.factory import get_llm_provider

        provider = get_llm_provider(settings)
        typer.secho("✓ LLM provider is accessible.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"✗ LLM provider error: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Check storage
    typer.echo("\nChecking storage...")
    try:
        settings.ensure_directories()
        assert settings.sqlite_path is not None
        assert settings.object_path is not None

        from synapse.storage.object_store import ObjectStore
        from synapse.storage.sqlite import SQLiteEventStore

        event_store = SQLiteEventStore(settings.sqlite_path)
        obj_store = ObjectStore(settings.object_path)
        typer.secho("✓ Storage is accessible.", fg=typer.colors.GREEN)
        typer.echo(f"  SQLite: {settings.sqlite_path.as_posix()}")
        typer.echo(f"  Objects: {settings.object_path.as_posix()}")
    except Exception as e:
        typer.secho(f"✗ Storage error: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho("\n✓ All systems operational.", fg=typer.colors.GREEN)
    typer.echo(f"Ready to run: synapse run {path}")


@app.command()
def run(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
    host: Annotated[str, typer.Option(help="Host to run the UI server on.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to run the UI server on.")] = 9876,
    skip_validation: Annotated[bool, typer.Option(help="Skip validation checks.")] = False,
) -> None:
    """Start the Synapse runtime with daemon, MCP, and UI services.

    This command:
    1. Validates configuration completeness
    2. Tests provider connectivity
    3. Starts the background daemon
    4. Starts the MCP server
    5. Starts the lightweight UI
    6. Shows health status

    Example:
        synapse run .
        synapse run . --port 9999
    """
    import subprocess
    import sys
    import time

    typer.secho("Starting Synapse Runtime", fg=typer.colors.CYAN, bold=True)

    settings = _settings(path)

    # Validate configuration first
    if not skip_validation:
        typer.echo("\nValidating configuration...")
        errors = settings.validate_configuration()
        if errors:
            typer.secho("Configuration errors found:", fg=typer.colors.RED, bold=True)
            for error in errors:
                typer.secho(f"  ✗ {error}", fg=typer.colors.RED)
            typer.echo(f"\nRun 'synapse setup {path}' to configure Synapse.")
            raise typer.Exit(code=1)
        typer.secho("✓ Configuration valid.", fg=typer.colors.GREEN)

        # Test provider connectivity
        typer.echo("\nTesting provider connectivity...")
        try:
            from synapse.provider.factory import get_llm_provider

            provider = get_llm_provider(settings)
            typer.secho("✓ LLM provider accessible.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"✗ Provider error: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    # Bootstrap runtime
    typer.echo("\nBootstrapping storage...")
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()
    typer.secho("✓ Storage ready.", fg=typer.colors.GREEN)

    # Start services
    typer.echo("\nStarting services...")
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
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append((name, p))
            time.sleep(0.5)  # Stagger startup

        typer.secho("\n✓ Services started successfully!", fg=typer.colors.GREEN, bold=True)
        for name, _ in processes:
            typer.secho(f"  ✓ {name} running", fg=typer.colors.GREEN)

        typer.secho(f"\nUI available at: http://{host}:{port}", fg=typer.colors.CYAN)

        typer.secho("\nNext steps:", fg=typer.colors.CYAN)
        typer.echo(f'  • Generate context: synapse task-context "your task" {path}')
        typer.echo(f"  • Check status: synapse status {path}")
        typer.echo("  • Press Ctrl+C to stop all services\n")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        typer.secho("\nShutting down services...", fg=typer.colors.YELLOW)
        for name, p in processes:
            p.terminate()
        for name, p in processes:
            p.wait(timeout=5)
        typer.secho("All services stopped.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED)
        for _, p in processes:
            p.terminate()
        raise typer.Exit(code=1)


@mcp_app.command("install")
def mcp_install(
    agent: Annotated[
        str, typer.Argument(help="Agent to install for (cursor, claude, roo, cline).")
    ],
    repo_path: Annotated[str, typer.Option(help="Repository path to bind to.")] = ".",
) -> None:
    """Auto-configure Synapse MCP in your IDE or agent.

    Supported agents: cursor, claude, roo, cline

    Examples:
        synapse mcp install cursor
        synapse mcp install claude
        synapse mcp install roo .
        synapse mcp install cline .
    """
    import sys

    from synapse.mcp.installer import MCPConfigError, get_mcp_installers

    agent = agent.lower()
    repo_abs = Path(repo_path).resolve().as_posix()
    executable = sys.executable

    # Build the MCP server command
    mcp_command = " ".join([executable, "-m", "synapse.cli", "mcp", "start", repo_abs])

    installers = get_mcp_installers()
    if agent not in installers:
        typer.secho(
            f"Unknown agent: {agent}. Supported: {', '.join(installers.keys())}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    typer.secho(
        f"Installing Synapse MCP for {agent.capitalize()}...",
        fg=typer.colors.CYAN,
        bold=True,
    )

    try:
        from typing import cast

        installer_class = installers[agent]
        # Dynamically call the installer class's static method
        config_path, success = cast(Any, installer_class).install(mcp_command)

        if success:
            typer.secho(f"✓ Successfully configured {agent.capitalize()}!", fg=typer.colors.GREEN)
            typer.echo(f"  Config: {config_path}")
            typer.echo(f"  Synapse repo: {repo_abs}")

            # Show next steps
            typer.secho("\nNext steps:", fg=typer.colors.CYAN)
            if agent == "cursor":
                typer.echo("  1. Restart Cursor")
                typer.echo("  2. Open the Composer or Chat")
                typer.echo("  3. Synapse MCP tools will be available")
            elif agent == "claude":
                typer.echo("  1. Restart Claude Desktop")
                typer.echo("  2. Start a new conversation")
                typer.echo("  3. Synapse tools will appear in the available tools list")
            elif agent in ("roo", "cline"):
                typer.echo(f"  1. Restart your {agent.capitalize()} extension")
                typer.echo("  2. Synapse tools will be available in the agent")

            typer.secho("\n✓ MCP Installation complete!", fg=typer.colors.GREEN)
        else:
            typer.secho(f"Installation failed for {agent}.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    except MCPConfigError as e:
        typer.secho(f"Configuration error: {e}", fg=typer.colors.RED)
        typer.echo("\nManual installation:")
        typer.echo(f"Add the following to your {agent} config:")
        mcp_config = {
            "mcpServers": {
                "synapse": {
                    "command": executable,
                    "args": ["-m", "synapse.cli", "mcp", "start", repo_abs],
                }
            }
        }
        typer.echo(json.dumps(mcp_config, indent=2))
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Error during installation: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@mcp_app.command("start")
def mcp_start(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Start the Model Context Protocol (MCP) server for agent integration."""
    typer.secho(f"Starting Synapse MCP Server for {path}...", fg=typer.colors.BLUE)

    # Force active mode and initialize runtime
    settings = _settings(path, json_output=json_output)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    from synapse.mcp.server import SynapseMCPServer

    server = SynapseMCPServer(runtime)
    asyncio.run(server.run())


@app.command()
def init(
    path: Annotated[str, typer.Argument(help="Repository path to initialize.")] = ".",
    force: Annotated[
        bool,
        typer.Option(help="Create a fresh context commit even if one exists."),
    ] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Initialize local Synapse state and create the first context commit."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    context_hash = runtime.bootstrap(force=force)
    _emit({"context_hash": context_hash, "state": "initialized"}, json_output=json_output)


@app.command()
def start(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
    low_power: Annotated[bool, typer.Option(help="Run daemon in low-power mode.")] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Start the local repository context daemon."""

    mode = RuntimeMode.LOW_POWER if low_power else RuntimeMode.ACTIVE
    settings = _settings(path, json_output=json_output, mode=mode)
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
def note(
    message: Annotated[str, typer.Argument(help="Manual context note.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Add a trusted manual context note."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    context_hash = runtime.add_note(message)
    _emit({"context_hash": context_hash, "state": "note_added"}, json_output=json_output)


@app.command()
def diff(
    left_hash: Annotated[str, typer.Argument(help="Left context hash.")],
    right_hash: Annotated[str, typer.Argument(help="Right context hash.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Compare two context commits."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.diff(left_hash, right_hash), json_output=json_output)


@app.command()
def rollback(
    target_hash: Annotated[str, typer.Argument(help="Context hash to activate.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Activate a previous context state without deleting history."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    runtime.rollback(target_hash)
    _emit({"context_hash": target_hash, "state": "rolled_back"}, json_output=json_output)


@app.command()
def doctor(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Run local integrity and replay checks."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.doctor(), json_output=json_output)


@app.command()
def commits(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    limit: Annotated[int, typer.Option(help="Maximum number of commits to show.")] = 20,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """List context commits."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit({"commits": runtime.list_context_commits(limit=limit)}, json_output=json_output)


@app.command()
def search(
    arg1: Annotated[str, typer.Argument(help="Query or repository path.")],
    arg2: Annotated[str, typer.Argument(help="Query (if arg1 is path).")] = "",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Search context using hybrid retrieval and grounded AI synthesis."""
    if arg2:
        path = arg1
        query = arg2
    else:
        path = "."
        query = arg1

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    typer.secho(f"Retrieving context for: '{query}'...", fg=typer.colors.BLUE)

    try:
        answer, sources, trace = runtime.query_hybrid(query)
        if json_output:
            _emit({"answer": answer, "sources": sources}, json_output=True)
            return

        typer.secho("\n--- SYNTHESIZED ANSWER ---", fg=typer.colors.GREEN, bold=True)
        typer.echo(answer)
        typer.secho("\n--- GROUNDING SOURCES ---", fg=typer.colors.MAGENTA, bold=True)
        for src in sources[:5]:
            uri = src.get("source_uri", "Unknown")
            kind = src.get("kind", "Node")
            typer.echo(f"• {uri} ({kind})")
    except Exception as exc:
        typer.secho(f"Error during retrieval: {exc}", fg=typer.colors.RED)


@app.command()
def task_context(
    task: Annotated[str, typer.Argument(help="Task description or scope.")] = "",
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
    limit: Annotated[int, typer.Option(help="Max tokens in response.")] = 4000,
) -> None:
    """Generate bounded context for a development task.

    This produces a task-specific context package including:
    - Affected files and their changes
    - Subsystem summaries
    - Dependencies and imports
    - Historical changes
    - Architectural risks

    Example:
        synapse task-context "refactor authentication pipeline" .
    """
    if not task:
        typer.secho("Task description required. Example:", fg=typer.colors.YELLOW)
        typer.echo('  synapse task-context "refactor auth flow" .')
        raise typer.Exit(code=1)

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    typer.secho(f"Generating context for task: '{task}'...", fg=typer.colors.BLUE)

    try:
        # Prepend task-focused prompt to ensure better scoping
        enhanced_query = (
            f"Generate a development context package for this task: {task}\n\n"
            "Include: affected files, subsystem boundaries, dependencies, "
            "recent changes, and architectural risks."
        )
        answer, sources, trace = runtime.query_hybrid(enhanced_query, max_tokens=limit)

        if json_output:
            _emit(
                {
                    "task": task,
                    "context": answer,
                    "sources": sources,
                    "retrieval_trace": trace,
                },
                json_output=True,
            )
            return

        typer.secho("\n--- TASK CONTEXT PACKAGE ---", fg=typer.colors.GREEN, bold=True)
        typer.echo(answer)
        typer.secho("\n--- GROUNDING SOURCES ---", fg=typer.colors.MAGENTA, bold=True)
        for src in sources[:10]:
            uri = src.get("source_uri", "Unknown")
            kind = src.get("kind", "Node")
            typer.echo(f"• {uri} ({kind})")

        if json_output is False:
            typer.secho("\nTo save this context:", fg=typer.colors.BRIGHT_BLACK)
            typer.echo(f'  synapse task-context "{task}" {path} --json > task-context.json')

    except ValueError as e:
        typer.secho(f"Configuration error: {e}", fg=typer.colors.RED)
        typer.echo("Run 'synapse setup' to initialize Synapse first.")
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.secho(f"Error during context generation: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@app.command()
def ui(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    host: Annotated[str, typer.Option(help="Host to run the UI server on.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to run the UI server on.")] = 9876,
) -> None:
    """Start the Synapse Visual Context UI and API server."""
    import uvicorn

    from synapse.api.app import create_app

    # Force active mode and initialize runtime
    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    api_app = create_app(runtime)
    typer.echo(f"Synapse Visual Explorer is running at http://{host}:{port}")
    uvicorn.run(api_app, host=host, port=port)
