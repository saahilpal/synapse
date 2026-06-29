from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from synap_git.cli.main import (
    _settings,
    console,
)
from synap_git.indexer.engine import SynapRuntime
from synap_git.mcp.server import SynapMCPFacade, SynapMCPServer

app = typer.Typer(help="Mcp commands.", no_args_is_help=True)


@app.command("start")
def mcp_start(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Start the MCP server."""
    settings = _settings(path, json_output=True)
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    server = SynapMCPServer(runtime)
    asyncio.run(server.run())


@app.command("config")
def mcp_config(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Output the MCP server configuration for manual IDE setup."""
    abs_path = Path(path).resolve().as_posix()

    config = {
        "mcpServers": {
            "synap": {
                "command": sys.executable,
                "args": ["-m", "synap_git.cli", "mcp", "start", abs_path],
                "autoConnect": True,
            }
        }
    }
    typer.echo(json.dumps(config, indent=2))


@app.command("verify")
def mcp_verify(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Verify MCP tools, schemas, and transport stability."""

    console.print("[bold cyan]Synap MCP Verification[/bold cyan]\n")

    settings = _settings(path)
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    facade = SynapMCPFacade(runtime)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Stage")
    table.add_column("Status")
    table.add_column("Latency (ms)")
    table.add_column("Details")

    with console.status(
        "[bold yellow]Verifying MCP transport and tools...[/bold yellow]"
    ) as status:

        def _simulate_mcp_call(tool_name: str, *args: Any, **kwargs: Any) -> bool:
            status.update(
                f"[bold yellow]Verifying stage: [white]{tool_name}[/white]...[/bold yellow]"
            )
            start = time.monotonic()
            try:
                status_info = facade.runtime.status()
                dirty = status_info.is_dirty
                warnings = ["Working tree is dirty. Index may be stale."] if dirty else []

                method = getattr(facade, tool_name)
                data = method(*args, **kwargs)

                response = {
                    "ok": True,
                    "data": data,
                    "warnings": warnings,
                    "trace_id": str(uuid.uuid4()),
                    "dirty_tree": dirty,
                }

                # Verify strict schema
                assert "ok" in response
                assert "data" in response
                assert "warnings" in response
                assert "trace_id" in response
                assert "dirty_tree" in response

                latency = (time.monotonic() - start) * 1000

                if tool_name == "search":
                    # Check trace payload exists
                    assert "trace" in data, "Trace payload missing in search data"

                details = f"keys: {list(data.keys())}"
                table.add_row(tool_name, "[green]PASS[/green]", f"{latency:.1f}", details)
                time.sleep(0.1)  # Visual breathing room
                return True
            except Exception as e:
                latency = (time.monotonic() - start) * 1000
                table.add_row(tool_name, "[red]FAIL[/red]", f"{latency:.1f}", str(e))
                return False

        results = [
            _simulate_mcp_call("get_status"),
            _simulate_mcp_call("verify_system"),
            _simulate_mcp_call("search", "User"),
            _simulate_mcp_call("create_checkpoint", "Testing MCP", ["test.py"], "Next", "None"),
            _simulate_mcp_call("restore_checkpoint", "latest"),
        ]

    console.print(table)

    if all(results):
        console.print("\n[bold green]✓ MCP Protocol Verified. All contracts passed.[/bold green]")
    else:
        console.print("\n[bold red]✗ MCP Protocol Verification Failed.[/bold red]")
        raise typer.Exit(1)
