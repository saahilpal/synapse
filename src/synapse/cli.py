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

    env_file = Path(path) / ".env"

    # 1. Choose Provider
    provider = typer.prompt(
        "Which primary LLM provider would you like to use? (ollama, openai, gemini, anthropic)",
        default="ollama",
    ).lower()

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
    embed_provider = typer.prompt("Which provider for embeddings?", default=provider).lower()

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

    env_content = f"""SYNAPSE_LLM_PROVIDER={provider}
SYNAPSE_LLM_MODEL={llm_model}
SYNAPSE_EMBED_PROVIDER={embed_provider}
SYNAPSE_EMBED_MODEL={embed_model}
SYNAPSE_OLLAMA_URL={ollama_url}
SYNAPSE_OPENAI_API_KEY={openai_key}
SYNAPSE_GEMINI_API_KEY={gemini_key}
SYNAPSE_ANTHROPIC_API_KEY={anthropic_key}
"""
    env_file.write_text(env_content)
    typer.secho(f"\n✓ Configuration saved to {env_file}", fg=typer.colors.GREEN)

    # 6. Initialize storage
    typer.echo("\nInitializing storage...")
    runtime = SynapseRuntime(_settings(path))
    runtime.bootstrap(force=True)
    typer.secho("✓ Storage initialized.", fg=typer.colors.GREEN)
    typer.echo("\nYou are all set! Next steps:")
    typer.echo(f"  1. Start the daemon: synapse start {path}")
    typer.echo(f"  2. Open the UI: synapse ui {path}")
    typer.echo(f'  3. Try a search: synapse search "What does this repository do?" {path}\n')


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
        answer, sources = runtime.query_hybrid(query)
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
