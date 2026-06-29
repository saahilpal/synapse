from __future__ import annotations

from datetime import datetime
from typing import Annotated

import typer
from rich.markdown import Markdown
from rich.table import Table

from synap_git.cli.main import (
    _settings,
    console,
)
from synap_git.indexer.engine import SynapRuntime

app = typer.Typer(help="Wiki commands.", no_args_is_help=True)


@app.command("list")
def wiki_list(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """List all generated wiki documentation pages."""
    runtime = SynapRuntime(_settings(path))
    wiki_dir = runtime.settings.state_path / "wiki"

    if not wiki_dir.exists():
        console.print("[yellow]No wiki documentation directory found.[/yellow]")
        return

    files = sorted(wiki_dir.glob("**/*.md"))
    if not files:
        console.print("[yellow]No wiki documentation pages found.[/yellow]")
        return

    table = Table(title="Generated Wiki Documentation", show_header=True, header_style="bold cyan")
    table.add_column("Wiki Page (Relative Path)")
    table.add_column("Size (Bytes)", justify="right")
    table.add_column("Last Modified")

    for f in files:
        rel_path = f.relative_to(wiki_dir).as_posix()
        stats = f.stat()
        mtime = datetime.fromtimestamp(stats.st_mtime).isoformat()
        table.add_row(
            rel_path,
            f"{stats.st_size:,}",
            mtime,
        )

    console.print(table)


@app.command("show")
def wiki_show(
    filepath: Annotated[
        str,
        typer.Argument(help="The relative path of the wiki page (e.g. src/utils.py.md)."),
    ],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show a specific wiki documentation page rendered in Markdown."""

    runtime = SynapRuntime(_settings(path))
    wiki_dir = runtime.settings.state_path / "wiki"

    target = filepath
    if not target.endswith(".md"):
        target += ".md"

    # Enforce lazy loading and refresh stale/missing pages on request
    with console.status(f"[yellow]Loading and refreshing '{target}'...[/yellow]"):
        try:
            runtime.wiki.ensure_wiki_page(target)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not refresh wiki page: {e}[/yellow]")

    wiki_path = wiki_dir / target
    if not wiki_path.exists():
        wiki_path = wiki_dir / filepath
        if not wiki_path.exists():
            console.print(f"[red]✗ Wiki page '{filepath}' not found.[/red]")
            raise typer.Exit(1)

    content = wiki_path.read_text(encoding="utf-8")
    console.print(Markdown(content))
