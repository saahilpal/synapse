from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

STATS_REL_PATH = Path(".synap") / "stats.json"

DEFAULT_ESTIMATION_METHOD = (
    "Estimated tokens saved by serving structural AST skeletons, symbol slices, "
    "and compact preambles instead of raw full source files."
)


def get_stats_path(repo_path: Path | str = ".") -> Path:
    """Return absolute or relative path to .synap/stats.json."""
    return Path(repo_path) / STATS_REL_PATH


def load_stats(repo_path: Path | str = ".") -> dict[str, Any]:
    """Load local cumulative statistics from .synap/stats.json.

    If file does not exist, returns initialized default structure.
    """
    path = get_stats_path(repo_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # Ensure all required keys exist
                data.setdefault("calls", 0)
                data.setdefault("tokens_served", 0)
                data.setdefault("estimated_tokens_avoided", 0)
                data.setdefault("estimation_method", DEFAULT_ESTIMATION_METHOD)
                data.setdefault("last_updated", "")
                data.setdefault("breakdown", {})
                return data
        except Exception:
            pass

    return {
        "calls": 0,
        "tokens_served": 0,
        "estimated_tokens_avoided": 0,
        "estimation_method": DEFAULT_ESTIMATION_METHOD,
        "last_updated": datetime.now(UTC).isoformat(),
        "breakdown": {},
    }


def save_stats(repo_path: Path | str, data: dict[str, Any]) -> None:
    """Persist local cumulative statistics to .synap/stats.json.

    Zero telemetry is sent; data remains strictly local in .synap.
    """
    path = get_stats_path(repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_usage(
    repo_path: Path | str,
    command: str,
    tokens_served: int,
    estimated_tokens_avoided: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a usage event into .synap/stats.json.

    command: Command or tool name (e.g., 'ctx', 'skeleton', 'find', 'remember').
    tokens_served: Number of tokens returned to the agent/caller.
    estimated_tokens_avoided: Estimated tokens avoided. If None, derived heuristically.
    """
    stats = load_stats(repo_path)

    # Heuristic estimation if not provided:
    # Based on average AST skeletonization savings (80-85% reduction)
    if estimated_tokens_avoided is None:
        if command in ("skeleton", "sk"):
            estimated_tokens_avoided = int(tokens_served * 6.5)
        elif command in ("ctx", "context", "preamble"):
            estimated_tokens_avoided = int(tokens_served * 7.0)
        elif command in ("find", "search"):
            estimated_tokens_avoided = int(tokens_served * 8.0)
        elif command in ("read_symbol", "explain"):
            estimated_tokens_avoided = int(tokens_served * 5.0)
        else:
            estimated_tokens_avoided = int(tokens_served * 4.0)

    stats["calls"] += 1
    stats["tokens_served"] += max(0, tokens_served)
    stats["estimated_tokens_avoided"] += max(0, estimated_tokens_avoided)
    stats["last_updated"] = datetime.now(UTC).isoformat()

    breakdown = stats.setdefault("breakdown", {})
    cmd_data = breakdown.setdefault(
        command, {"calls": 0, "tokens_served": 0, "estimated_tokens_avoided": 0}
    )
    cmd_data["calls"] += 1
    cmd_data["tokens_served"] += max(0, tokens_served)
    cmd_data["estimated_tokens_avoided"] += max(0, estimated_tokens_avoided)

    save_stats(repo_path, stats)
    return stats


def stats_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    json_output: Annotated[
        bool, typer.Option("--json", help="Output statistics in JSON format.")
    ] = False,
    reset: Annotated[
        bool, typer.Option("--reset", help="Reset cumulative statistics counters to zero.")
    ] = False,
) -> None:
    """Show local cumulative token efficiency and avoided token metrics."""
    if reset:
        new_stats = {
            "calls": 0,
            "tokens_served": 0,
            "estimated_tokens_avoided": 0,
            "estimation_method": DEFAULT_ESTIMATION_METHOD,
            "last_updated": datetime.now(UTC).isoformat(),
            "breakdown": {},
        }
        save_stats(path, new_stats)
        if json_output:
            typer.echo(json.dumps({"status": "reset", "stats": new_stats}))
        else:
            console.print(
                "[bold yellow]✔ Local cumulative stats have been reset to zero.[/bold yellow]"
            )
        return

    stats = load_stats(path)

    if json_output:
        typer.echo(json.dumps(stats, indent=2))
        return

    calls = stats["calls"]
    served = stats["tokens_served"]
    avoided = stats["estimated_tokens_avoided"]
    total = served + avoided
    savings_pct = (avoided / total * 100.0) if total > 0 else 0.0

    table = Table(
        title="📊 Synapse Local Token Efficiency (No Telemetry)",
        border_style="cyan",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="bold green", justify="right")
    table.add_column("Details & Methodology", style="white")

    table.add_row(
        "Total Agent / Tool Calls",
        f"{calls:,}",
        "Cumulative invocations recorded locally",
    )
    table.add_row(
        "Tokens Served",
        f"{served:,}",
        "AST skeletons, symbol slices & compact preambles returned",
    )
    table.add_row(
        "Estimated Tokens Avoided",
        f"{avoided:,}",
        f"ESTIMATE: {stats['estimation_method']}",
    )
    table.add_row(
        "Estimated Efficiency Gain",
        f"{savings_pct:.1f}%",
        "Tokens spared from context windows vs raw file reads",
    )

    console.print(table)

    breakdown = stats.get("breakdown", {})
    if breakdown:
        b_table = Table(
            title="Breakdown by Operation",
            border_style="dim",
            show_header=True,
            header_style="bold blue",
        )
        b_table.add_column("Operation", style="cyan")
        b_table.add_column("Calls", justify="right")
        b_table.add_column("Tokens Served", justify="right")
        b_table.add_column("Est. Avoided", justify="right")
        b_table.add_column("Est. Savings %", justify="right")

        for cmd, d in sorted(breakdown.items()):
            c_calls = d["calls"]
            c_served = d["tokens_served"]
            c_avoided = d["estimated_tokens_avoided"]
            c_tot = c_served + c_avoided
            c_pct = (c_avoided / c_tot * 100.0) if c_tot > 0 else 0.0
            b_table.add_row(
                cmd,
                f"{c_calls:,}",
                f"{c_served:,}",
                f"{c_avoided:,}",
                f"{c_pct:.1f}%",
            )
        console.print(b_table)

    console.print(
        Panel(
            f"[bold]Methodology Note:[/bold] {stats['estimation_method']}\n"
            f"[dim]Stats stored strictly in {get_stats_path(path)}. Zero network telemetry is transmitted.[/dim]",
            border_style="dim",
        )
    )
