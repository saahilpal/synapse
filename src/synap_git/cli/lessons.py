from __future__ import annotations

from typing import Annotated

import questionary
import typer
from rich.panel import Panel
from rich.table import Table

from synap_git.cli.main import (
    JSON_OPTION,
    _emit,
    _settings,
    console,
)
from synap_git.indexer.engine import SynapRuntime

app = typer.Typer(help="Lessons commands.", no_args_is_help=True)


@app.command("list")
def lessons_list(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    status: Annotated[
        str,
        typer.Option(
            "--status",
            "-s",
            help="Filter by status: pending, approved, rejected, or all.",
        ),
    ] = "all",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """List recorded architectural lessons."""
    runtime = SynapRuntime(_settings(path, json_output=json_output))
    lessons = runtime.store.get_lessons(status)

    if json_output:
        _emit({"lessons": lessons}, json_output=True)
        return

    if not lessons:
        console.print(f"[yellow]No lessons found matching status '{status}'.[/yellow]")
        return

    table = Table(title=f"Synap Lessons ({status})", show_header=True, header_style="bold cyan")
    table.add_column("Lesson ID", style="dim")
    table.add_column("Status")
    table.add_column("What Failed")
    table.add_column("Why / Lesson")
    table.add_column("Revert Commit", style="dim")

    for item in lessons:
        item_status = item.get("status", "unknown")
        if item_status == "approved":
            status_style = "[green]approved[/green]"
        elif item_status == "pending":
            status_style = "[yellow]pending[/yellow]"
        elif item_status == "rejected":
            status_style = "[red]rejected[/red]"
        else:
            status_style = item_status

        table.add_row(
            item.get("lesson_id", "")[:12] + "…",
            status_style,
            (item.get("what_failed") or "")[:40]
            + ("…" if len(item.get("what_failed") or "") > 40 else ""),
            (item.get("why_failed") or "")[:45]
            + ("…" if len(item.get("why_failed") or "") > 45 else ""),
            (item.get("revert_commit") or "")[:8],
        )

    console.print(table)


@app.command("approve")
def lessons_approve(
    lesson_id: Annotated[str, typer.Argument(help="The ID of the lesson to approve.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Approve a pending lesson."""
    runtime = SynapRuntime(_settings(path))
    # Fetch to ensure it exists and is pending
    pending = runtime.store.get_lessons("pending")
    target = next((lesson for lesson in pending if lesson["lesson_id"] == lesson_id), None)

    if not target:
        console.print(f"[red]✗ Pending lesson {lesson_id} not found.[/red]")
        raise typer.Exit(1)

    runtime.store.update_lesson(lesson_id, target["why_failed"], "approved", actor="cli_user")
    console.print(f"[green]✓ Lesson {lesson_id} approved. Memory updated.[/green]")


@app.command("review")
def lessons_review(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Interactively review and manage pending lessons."""

    runtime = SynapRuntime(_settings(path))
    pending = runtime.store.get_lessons("pending")

    if not pending:
        console.print("[yellow]No pending lessons to review.[/yellow]")
        return

    console.print(f"[bold cyan]Reviewing {len(pending)} pending lessons...[/bold cyan]\n")

    approved_count = 0
    rejected_count = 0
    skipped_count = 0

    for lesson in pending:
        lesson_id = lesson["lesson_id"]

        # Build detail view
        details = (
            f"[bold]Revert Commit:[/bold] {lesson['revert_commit'][:8]}\n"
            f"[bold]Reverted From:[/bold] {lesson['reverted_from'][:8]}\n"
            f"[bold]Files Affected:[/bold] {lesson['files_affected']}\n"
            f"[bold]What Failed:[/bold] {lesson['what_failed']}\n"
            f"[bold]Proposed Lesson:[/bold] {lesson['why_failed']}"
        )

        console.print(Panel(details, title=f"Lesson {lesson_id[:8]}", expand=False))

        choice = questionary.select(
            "Action:",
            choices=[
                questionary.Choice("Approve", value="approve"),
                questionary.Choice("Edit & Approve", value="edit"),
                questionary.Choice("Reject", value="reject"),
                questionary.Choice("Skip", value="skip"),
            ],
        ).ask()

        if choice == "approve":
            runtime.store.update_lesson(
                lesson_id, lesson["why_failed"], "approved", actor="cli_user"
            )
            console.print("[green]✓ Approved.[/green]\n")
            approved_count += 1
        elif choice == "edit":
            edited = questionary.text("Edit lesson text:", default=lesson["why_failed"]).ask()
            if edited:
                runtime.store.update_lesson(lesson_id, edited, "approved", actor="cli_user")
                console.print("[green]✓ Edited and Approved.[/green]\n")
                approved_count += 1
            else:
                console.print("[yellow]Skipping edit.[/yellow]\n")
                skipped_count += 1
        elif choice == "reject":
            runtime.store.update_lesson(
                lesson_id, lesson["why_failed"], "rejected", actor="cli_user"
            )
            console.print("[red]✗ Rejected.[/red]\n")
            rejected_count += 1
        elif choice == "skip":
            console.print("[yellow]Skipped.[/yellow]\n")
            skipped_count += 1
        else:
            console.print("[yellow]Aborting review.[/yellow]")
            break

    console.print("[bold cyan]Review Summary:[/bold cyan]")
    console.print(f"  [green]Approved:[/green] {approved_count}")
    console.print(f"  [red]Rejected:[/red] {rejected_count}")
    console.print(f"  [yellow]Skipped:[/yellow]  {skipped_count}")


@app.command("reject")
def lessons_reject(
    lesson_id: Annotated[str, typer.Argument(help="The ID of the lesson to reject.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Reject a pending or approved lesson."""
    runtime = SynapRuntime(_settings(path))
    pending = runtime.store.get_lessons("pending")
    approved = runtime.store.get_lessons("approved")
    target = next(
        (lesson for lesson in pending + approved if lesson["lesson_id"] == lesson_id), None
    )

    if not target:
        console.print(f"[red]✗ Lesson {lesson_id} not found in pending or approved queues.[/red]")
        raise typer.Exit(1)

    runtime.store.update_lesson(lesson_id, target["why_failed"], "rejected", actor="cli_user")
    console.print(f"[yellow]✓ Lesson {lesson_id} rejected. Memory updated.[/yellow]")
