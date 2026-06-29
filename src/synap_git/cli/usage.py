from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.panel import Panel
from rich.table import Table

from synap_git.cli.main import (
    _settings,
    console,
)
from synap_git.indexer.engine import SynapRuntime

app = typer.Typer(help="Usage commands.", no_args_is_help=True)


@app.command("show")
def usage_show(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show detailed LLM call and token usage metrics."""
    runtime = SynapRuntime(_settings(path))
    calls = runtime.store.get_llm_calls()

    if not calls:
        console.print("[yellow]No LLM calls recorded yet.[/yellow]")
        return

    # Aggregate by provider/model/purpose
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    total_input = 0
    total_output = 0

    for c in calls:
        key = (c["provider"], c["model"], c["purpose"])
        if key not in agg:
            agg[key] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
        agg[key]["calls"] += 1
        agg[key]["input_tokens"] += c["input_tokens"]
        agg[key]["output_tokens"] += c["output_tokens"]

        total_input += c["input_tokens"]
        total_output += c["output_tokens"]

    # Render summary table
    table = Table(title="LLM Call Aggregated Usage", show_header=True, header_style="bold cyan")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Purpose")
    table.add_column("Calls", justify="right")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")

    for (prov, model, purpose), data in sorted(agg.items()):
        table.add_row(
            prov,
            model,
            purpose,
            str(data["calls"]),
            f"{data['input_tokens']:,}",
            f"{data['output_tokens']:,}",
        )

    console.print(table)

    # Grand total box

    grand_total_text = (
        f"[bold]Total Calls:[/bold] {len(calls)}\n"
        f"[bold]Total Input Tokens:[/bold] {total_input:,}\n"
        f"[bold]Total Output Tokens:[/bold] {total_output:,}"
    )
    console.print(Panel(grand_total_text, title="Operational Usage Summary", expand=False))


@app.command("clear")
def usage_clear(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Clear all LLM call usage history."""
    runtime = SynapRuntime(_settings(path))
    runtime.store.clear_llm_calls()
    console.print("[green]✓ LLM usage history cleared successfully.[/green]")
