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
    help="Temporal cognition runtime for software systems.",
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
    """Start the local cognitive runtime daemon."""

    mode = RuntimeMode.LOW_POWER if low_power else RuntimeMode.ACTIVE
    settings = _settings(path, json_output=json_output, mode=mode)
    daemon = RuntimeDaemon(settings)
    asyncio.run(daemon.start())


@app.command()
def status(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show current cognitive runtime status."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.status(), json_output=json_output)


@app.command()
def note(
    message: Annotated[str, typer.Argument(help="Manual cognition note.")],
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


@app.command("impact")
def impact(
    left_hash: Annotated[str, typer.Argument(help="Left context hash.")],
    right_hash: Annotated[str, typer.Argument(help="Right context hash.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Explain architectural impact between two context commits."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.semantic_impact(left_hash, right_hash), json_output=json_output)


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
def drift(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Detect initial documentation and source drift."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    findings = runtime.drift()
    _emit({"findings": findings, "count": len(findings)}, json_output=json_output)


@app.command()
def health(
    context_hash: Annotated[str | None, typer.Option(help="Context hash to analyze.")] = None,
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Analyze architecture health and coupling metrics."""
    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.analyze_health(context_hash), json_output=json_output)


@app.command("merge-conflicts")
def merge_conflicts(
    left: Annotated[str, typer.Argument(help="Left branch head or context hash.")],
    right: Annotated[str, typer.Argument(help="Right branch head or context hash.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Evaluate branch divergence and detect cognitive merge conflicts."""
    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.detect_conflicts(left, right), json_output=json_output)


@app.command()
def compact(
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Trigger cognition database compaction and cold archival."""
    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.compact(), json_output=json_output)


@app.command()
def doctor(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Run local integrity and replay checks."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.doctor(), json_output=json_output)


@app.command("lineage")
def lineage(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Run cognition lineage fsck checks."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.lineage(), json_output=json_output)


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
def timeline(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    branch: Annotated[str | None, typer.Option(help="Limit timeline to a branch.")] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of timeline events.")] = 50,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show cognitive evolution timeline."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit({"events": runtime.timeline(branch=branch, limit=limit)}, json_output=json_output)


@app.command()
def assumptions(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    context_hash: Annotated[
        str | None,
        typer.Option("--context", help="Context hash to inspect."),
    ] = None,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """List active and invalidated architectural assumptions."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(
        {"assumptions": runtime.assumptions(context_hash=context_hash)},
        json_output=json_output,
    )


@app.command("invalidate-assumptions")
def invalidate_assumptions(
    left_hash: Annotated[str, typer.Argument(help="Earlier context hash.")],
    right_hash: Annotated[str, typer.Argument(help="Later context hash.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    apply: Annotated[bool, typer.Option(help="Persist invalidation on matching rows.")] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Detect assumptions invalidated between two context states."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(
        {
            "invalidated": runtime.invalidated_assumptions(
                left_hash=left_hash,
                right_hash=right_hash,
                apply=apply,
            )
        },
        json_output=json_output,
    )


@app.command("confidence")
def confidence(
    stable_id: Annotated[str, typer.Argument(help="Semantic object stable ID.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show confidence(t) for a cognition object."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.confidence_evolution(stable_id), json_output=json_output)


@app.command("confidence-decay")
def confidence_decay(
    stable_id: Annotated[str, typer.Argument(help="Semantic object stable ID.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Query confidence decay for a cognition object."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.query_confidence_decay(stable_id), json_output=json_output)


@app.command("replay-cognition")
def replay_cognition(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    context_hash: Annotated[
        str | None,
        typer.Option("--context", help="Replay to this context hash."),
    ] = None,
    branch: Annotated[str | None, typer.Option(help="Replay branch timeline.")] = None,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Replay semantic, assumption, and confidence evolution."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(
        runtime.replay_cognition(context_hash=context_hash, branch=branch),
        json_output=json_output,
    )


@app.command("branch-divergence")
def branch_divergence(
    left_branch: Annotated[str, typer.Argument(help="Left branch.")],
    right_branch: Annotated[str, typer.Argument(help="Right branch.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Inspect cognitive divergence between two branch heads."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(
        runtime.branch_divergence(left_branch=left_branch, right_branch=right_branch),
        json_output=json_output,
    )


@app.command("temporal-graph")
def temporal_graph(
    context_hash: Annotated[str, typer.Argument(help="Context hash to reconstruct.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Reconstruct temporal cognition facts at a context head."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.temporal_graph(context_hash), json_output=json_output)


@app.command("incident")
def incident(
    title: Annotated[str, typer.Argument(help="Incident title.")],
    summary: Annotated[str, typer.Argument(help="Incident summary.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Link an incident to the active cognition state."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit(runtime.record_incident(title=title, summary=summary), json_output=json_output)


@app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="Cognition query.")],
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    limit: Annotated[int, typer.Option(help="Maximum results.")] = 20,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Search semantic cognition objects."""

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    _emit({"results": runtime.search_cognition(query, limit=limit)}, json_output=json_output)


@app.command()
def ui(
    path: Annotated[str, typer.Option(help="Repository path.")] = ".",
    host: Annotated[str, typer.Option(help="Host to run the UI server on.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to run the UI server on.")] = 9876,
) -> None:
    """Start the Synapse Visual Cognition UI and API server."""
    import uvicorn

    from synapse.api.app import create_app

    # Force active mode and initialize runtime
    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    api_app = create_app(runtime)
    typer.echo(f"Synapse Visual Explorer is running at http://{host}:{port}")
    uvicorn.run(api_app, host=host, port=port)
