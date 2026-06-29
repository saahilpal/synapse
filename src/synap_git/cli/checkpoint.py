from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

import typer
from rich.table import Table

from synap_git.cli.main import (
    _settings,
    console,
)
from synap_git.indexer.engine import SynapRuntime

app = typer.Typer(help="Checkpoint commands.", no_args_is_help=True)


@app.command("create")
def checkpoint_create(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    doing: Annotated[
        str, typer.Option(help="What the agent is currently doing.")
    ] = "Manual snapshot",
    files: Annotated[str, typer.Option(help="Comma-separated list of changed files.")] = "",
    next_step: Annotated[str, typer.Option(help="The next step to be taken.")] = "",
    blockers: Annotated[str, typer.Option(help="Current blockers or obstacles.")] = "",
) -> None:
    """Create a new context checkpoint."""
    runtime = SynapRuntime(_settings(path))

    checkpoint_id = str(uuid.uuid4())
    status = runtime.status()
    branch = status.branch
    commit = status.git_commit or "unknown"

    file_list = [f.strip() for f in files.split(",") if f.strip()]

    runtime.store.put_checkpoint(
        checkpoint_id=checkpoint_id,
        branch=branch,
        commit_hash=commit,
        doing=doing,
        changed_files=json.dumps(file_list),
        next_step=next_step,
        blockers=blockers,
    )
    console.print(f"[green]✓ Checkpoint {checkpoint_id} created for branch '{branch}'.[/green]")


@app.command("list")
def checkpoint_list(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """List checkpoints for the active branch."""
    runtime = SynapRuntime(_settings(path))
    status = runtime.status()
    branch = status.branch
    cps = runtime.store.get_checkpoints(branch)

    if not cps:
        console.print(f"[yellow]No checkpoints found for branch '{branch}'.[/yellow]")
        return

    table = Table(
        title=f"Checkpoints for branch '{branch}'", show_header=True, header_style="bold cyan"
    )
    table.add_column("Checkpoint ID")
    table.add_column("Commit Hash")
    table.add_column("Doing")
    table.add_column("Changed Files")
    table.add_column("Created At")

    for cp in cps:
        created = datetime.fromtimestamp(cp["created_at"]).isoformat()
        try:
            ch_files = ", ".join(json.loads(cp["changed_files"]))
        except Exception:
            ch_files = cp["changed_files"]
        table.add_row(
            cp["checkpoint_id"][:16] + "…",
            cp["commit_hash"][:7],
            cp["doing"],
            ch_files if ch_files else "None",
            created,
        )
    console.print(table)


@app.command("restore")
def checkpoint_restore(
    checkpoint_id: Annotated[
        str, typer.Argument(help="The ID of the checkpoint to restore (defaults to latest).")
    ] = "latest",
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Restore and show details of a checkpoint."""
    runtime = SynapRuntime(_settings(path))
    status = runtime.status()
    branch = status.branch

    if checkpoint_id == "latest":
        cp = runtime.store.get_latest_checkpoint(branch)
    else:
        cp = runtime.store.get_checkpoint(checkpoint_id)

    if not cp:
        console.print(f"[red]✗ Checkpoint '{checkpoint_id}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold green]✓ Checkpoint '{cp['checkpoint_id']}' details:[/bold green]")
    console.print(f"  [bold]Branch:[/bold] {cp['branch']}")
    console.print(f"  [bold]Commit:[/bold] {cp['commit_hash']}")
    console.print(f"  [bold]Doing:[/bold] {cp['doing']}")
    try:
        ch_files = ", ".join(json.loads(cp["changed_files"]))
    except Exception:
        ch_files = cp["changed_files"]
    console.print(f"  [bold]Changed Files:[/bold] {ch_files if ch_files else 'None'}")
    console.print(f"  [bold]Next Step:[/bold] {cp['next_step'] or 'None'}")
    console.print(f"  [bold]Blockers:[/bold] {cp['blockers'] or 'None'}")
    console.print(
        f"  [bold]Created At:[/bold] {datetime.fromtimestamp(cp['created_at']).isoformat()}"
    )
