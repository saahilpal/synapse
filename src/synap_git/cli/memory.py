from __future__ import annotations

import json as json_lib
from typing import Annotated, Any

import typer
from rich.table import Table

from synap_git.cli.main import (
    JSON_OPTION,
    _emit,
    _settings,
    console,
)
from synap_git.indexer.engine import SynapRuntime

app = typer.Typer(help="Memory commands.", no_args_is_help=True)


@app.command("status")
def memory_status(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show current memory trust status."""
    runtime = SynapRuntime(_settings(path))

    approved = runtime.store.get_lessons("approved")
    pending = runtime.store.get_lessons("pending")
    expired = runtime.store.get_lessons("expired")

    table = Table(title="Synap Memory Status", show_header=True, header_style="bold cyan")
    table.add_column("State")
    table.add_column("Count")

    table.add_row("[green]Approved[/green]", str(len(approved)))
    table.add_row("[yellow]Pending[/yellow]", str(len(pending)))
    table.add_row("[dim]Expired[/dim]", str(len(expired)))

    console.print(table)


@app.command("prune")
def memory_prune(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Evaluate expiry rules and prune dead memory."""
    runtime = SynapRuntime(_settings(path))
    pruned_count = runtime.store.prune_expired_lessons()
    console.print(f"[green]✓ Evaluated memory expiry. Pruned {pruned_count} lessons.[/green]")


@app.command("verify")
def memory_verify(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Check for dangling file references in approved memory lessons."""

    runtime = SynapRuntime(_settings(path, json_output=json_output))
    approved = runtime.store.get_lessons("approved")

    dangling: list[dict[str, Any]] = []
    healthy: list[dict[str, Any]] = []

    repo_root = runtime.settings.repository_path

    for lesson in approved:
        lesson_id = lesson["lesson_id"]
        try:
            files: list[str] = json_lib.loads(lesson.get("files_affected") or "[]")
        except Exception:
            files = []

        missing = [f for f in files if not (repo_root / f).exists()]
        if missing:
            dangling.append({"lesson_id": lesson_id, "missing_files": missing})
        else:
            healthy.append({"lesson_id": lesson_id, "files": files})

    if json_output:
        _emit({"dangling": dangling, "healthy": healthy}, json_output=True)
        return

    if not approved:
        console.print("[dim]No approved lessons to verify.[/dim]")
        return

    table = Table(title="Approved Memory Verification", show_header=True, header_style="bold cyan")
    table.add_column("Lesson ID")
    table.add_column("Status")
    table.add_column("Details")

    for item in healthy:
        table.add_row(
            item["lesson_id"][:16] + "…",
            "[green]HEALTHY[/green]",
            f"{len(item['files'])} file(s) intact",
        )
    for item in dangling:
        table.add_row(
            item["lesson_id"][:16] + "…",
            "[red]DANGLING[/red]",
            f"Missing: {', '.join(item['missing_files'])}",
        )

    console.print(table)

    if dangling:
        console.print(
            f"\n[bold yellow]⚠ {len(dangling)} lesson(s) reference files no longer in the repository.[/bold yellow]"
        )
        console.print("[dim]Run `synap lessons reject <id>` to clean up stale memory.[/dim]")
    else:
        console.print("\n[green]✓ All approved memory references are valid.[/green]")
