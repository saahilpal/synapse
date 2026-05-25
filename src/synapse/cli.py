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
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
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
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Compare two context commits."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.diff(left_hash, right_hash), json_output=json_output)


@app.command()
def rollback(
    target_hash: Annotated[str, typer.Argument(help="Context hash to activate.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
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
    query: Annotated[str, typer.Argument(help="Semantic context query.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    limit: Annotated[int, typer.Option(help="Maximum results.")] = 20,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Search semantic annotations."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit({"results": runtime.search_context(query, limit=limit)}, json_output=json_output)


@app.command()
def ui(
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
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
