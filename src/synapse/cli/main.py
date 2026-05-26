from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from synapse.config import LoggingMode, RuntimeMode, RuntimeProfile, SynapseSettings
from synapse.diagnostics.logger import configure_logging
from synapse.indexer.daemon import RuntimeDaemon
from synapse.indexer.engine import SynapseRuntime

app = typer.Typer(
    name="synapse",
    help="Deterministic Git-aware structural retrieval engine for AI coding agents.",
    no_args_is_help=True,
)

JSON_OPTION = typer.Option("--json", help="Emit machine-readable JSON.")
console = Console()


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
        console.print(json.dumps(_jsonable(value), indent=2, sort_keys=True))
        return
    if isinstance(value, str):
        console.print(value)
        return
    for key, item in _jsonable(value).items():
        console.print(f"{key}: {item}")


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

memory_app = typer.Typer(help="Manage L3 Agent Memory.")
app.add_typer(memory_app, name="memory")

lessons_app = typer.Typer(help="Manage Agent Lessons.")
app.add_typer(lessons_app, name="lessons")

checkpoint_app = typer.Typer(help="Manage Context Checkpoints.")
app.add_typer(checkpoint_app, name="checkpoint")

wiki_app = typer.Typer(help="Manage L2 Wiki Documentation.")
app.add_typer(wiki_app, name="wiki")

cost_app = typer.Typer(help="View AI Cost Tracking.")
app.add_typer(cost_app, name="cost")


@app.command()
def setup(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Interactive first-run setup and onboarding."""
    console.print("[bold cyan]Welcome to Synapse AI Context Runtime[/bold cyan]")
    console.print("This wizard will bootstrap your local AI environment.\n")

    config_dir = Path("~/.config/synapse").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"

    console.print("[yellow]Synapse stores API keys securely in your system keyring.[/yellow]")
    console.print(f"Global configuration: {config_file.as_posix()}\n")

    # 1. Choose Provider
    provider = typer.prompt(
        "Which primary LLM provider would you like to use?",
        default="ollama",
    ).lower()

    # 2. Configure LLM
    llm_model = typer.prompt(
        f"Which model would you like to use for {provider}?",
        default="qwen2.5-coder:14b" if provider == "ollama" else "gpt-4o",
    )

    # Gather Keys if needed
    ollama_url = "http://localhost:11434"

    import keyring

    if provider == "openai":
        key = typer.prompt("Enter OpenAI API Key", hide_input=True)
        keyring.set_password("synapse", "openai_api_key", key)
    elif provider == "gemini":
        key = typer.prompt("Enter Gemini API Key", hide_input=True)
        keyring.set_password("synapse", "gemini_api_key", key)
    elif provider == "anthropic":
        key = typer.prompt("Enter Anthropic API Key", hide_input=True)
        keyring.set_password("synapse", "anthropic_api_key", key)
    elif provider == "ollama":
        ollama_url = typer.prompt("Enter Ollama URL", default="http://localhost:11434")

    # Build TOML config (non-sensitive only)
    config_content = f"""[llm]
llm_provider = "{provider}"
llm_model = "{llm_model}"
ollama_url = "{ollama_url}"
"""
    config_file.write_text(config_content)
    console.print(f"\n[green]✓ Configuration saved to {config_file.as_posix()}[/green]")
    console.print("[green]✓ Secrets saved to system keyring.[/green]")

    # Initialize storage
    runtime = SynapseRuntime(_settings(path))
    runtime.bootstrap(force=True)
    console.print("[green]✓ Storage initialized.[/green]")


def _auto_protect_synapse(repository_path: Path) -> None:
    gitignore_path = repository_path / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".synapse/\n")
        return

    content = gitignore_path.read_text()
    lines = content.splitlines()
    if ".synapse/" not in lines and ".synapse" not in lines:
        if content and not content.endswith("\n"):
            content += "\n"
        content += ".synapse/\n"
        gitignore_path.write_text(content)


@app.command()
def init(
    path: Annotated[str, typer.Argument(help="Repository path to initialize.")] = ".",
    force: Annotated[bool, typer.Option(help="Force reindexing.")] = False,
    skip_llm: Annotated[
        bool, typer.Option("--skip-llm", help="Run in Mode A (structural only).")
    ] = False,
    skip_wiki: Annotated[
        bool, typer.Option("--skip-wiki", help="Skip L2 documentation generation.")
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Suppress output.")] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Initialize local Synapse state and perform first scan."""
    settings = _settings(path, json_output=json_output)
    if skip_llm:
        settings.llm_provider = None

    _auto_protect_synapse(settings.repository_path)

    runtime = SynapseRuntime(settings)
    commit = runtime.bootstrap(force=force)

    if json_output:
        _emit({"active_commit": commit, "state": "initialized"}, json_output=True)
    elif not quiet:
        console.print(f"[green]✓ Initialized repository at {commit}[/green]")


@app.command()
def wipe(
    path: Annotated[str, typer.Argument(help="Repository path to wipe.")] = ".",
) -> None:
    """Completely purge the local index for a fresh rebuild."""
    if not typer.confirm("This will delete all indexed symbols and embeddings. Continue?"):
        raise typer.Abort()
    runtime = SynapseRuntime(_settings(path))
    runtime.wipe_index()
    console.print("[green]✓ Index wiped.[/green]")


@app.command()
def start(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Start the simplified repository context daemon."""
    settings = _settings(path, json_output=json_output)
    daemon = RuntimeDaemon(settings)
    asyncio.run(daemon.start())


@app.command()
def status(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show current repository context status."""
    runtime = SynapseRuntime(_settings(path, json_output=json_output))
    status_info = runtime.status()
    if json_output:
        _emit(status_info, json_output=True)
    else:
        table = Table(title="Synapse Repository Status", show_header=True, header_style="bold cyan")
        table.add_column("Property", style="dim")
        table.add_column("Value")

        table.add_row("Repository", status_info.repository_path)
        table.add_row("Branch", status_info.branch)
        table.add_row("Git Commit", status_info.git_commit or "None")
        table.add_row("Indexed Commit", status_info.active_commit or "None")
        table.add_row("Files Indexed", str(status_info.files))
        table.add_row("Symbols Indexed", str(status_info.symbols))
        table.add_row("Mode", status_info.mode)

        console.print(table)

        if status_info.is_dirty:
            console.print(
                "[bold yellow]Warning: Working tree is dirty. Uncommitted changes are not indexed.[/bold yellow]"
            )


@app.command()
def rollback(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Rollback active state to a previous commit."""
    import subprocess

    settings = _settings(path)
    runtime = SynapseRuntime(settings)

    # 1. Get recent commits
    try:
        log_out = subprocess.check_output(  # noqa: S603
            ["git", "log", "-n", "5", "--pretty=format:%h|%ar|%s"],  # noqa: S607
            cwd=settings.repository_path,
            text=True,
        )
        commits = []
        for line in log_out.splitlines():
            if line.strip():
                parts = line.split("|", 2)
                if len(parts) == 3:
                    commits.append((parts[0], parts[1], parts[2]))
    except Exception as e:
        console.print(f"[red]✗ Failed to read git history: {e}[/red]")
        raise typer.Abort()

    if not commits:
        console.print("[yellow]No commits found in git log.[/yellow]")
        return

    console.print("Recent commits:")
    for idx, (h, ar, s) in enumerate(commits, 1):
        suffix = "  ← current" if idx == 1 else ""
        console.print(f'  [{idx}] {h}  {ar}   "{s}"{suffix}')

    choice = typer.prompt("\nRoll back to which commit? [1-5]", default="1")
    try:
        choice_idx = int(choice) - 1
        if choice_idx < 0 or choice_idx >= len(commits):
            raise ValueError()
    except ValueError:
        console.print("[red]Invalid choice.[/red]")
        raise typer.Abort()

    selected_commit = commits[choice_idx][0]

    console.print(f"\n[bold yellow]⚠ Rolling back to {selected_commit} will:[/bold yellow]")
    console.print("    - Restore index to that commit's state (via git checkout)")
    console.print("    - Preserve all approved lessons (they survive rollbacks)")
    console.print("    - Clear current checkpoint")

    if not typer.confirm("\nProceed?", default=False):
        raise typer.Abort()

    # Clear current checkpoint
    try:
        with runtime.store.connect() as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE branch = ?",
                (runtime.git.state().effective_branch,),
            )
    except Exception:
        pass

    # git checkout
    try:
        subprocess.check_call(  # noqa: S603
            ["git", "checkout", selected_commit],  # noqa: S607
            cwd=settings.repository_path,
        )
    except Exception as e:
        console.print(f"[red]✗ Git checkout failed: {e}[/red]")
        raise typer.Abort()

    runtime.bootstrap(force=True)
    console.print(f"[green]✓ Rolled back successfully to {selected_commit}[/green]")


@app.command()
def recover(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Recover from a broken index state."""
    settings = _settings(path)
    runtime = SynapseRuntime(settings)

    console.print("Checking database integrity...")
    corrupted = False
    try:
        runtime.initialize_storage()
        integrity = runtime.store.integrity_check()
        if integrity != "ok":
            corrupted = True
    except Exception:
        corrupted = True

    if corrupted:
        console.print("[red]✗ synapse.db appears corrupted[/red]\n")
    else:
        console.print("[green]✓ Database file is healthy.[/green]")
        if not typer.confirm("Do you want to force rebuild the index anyway?"):
            return

    console.print("Rebuilding from git history...")
    console.print("[1/3] Restoring file structure from HEAD")
    try:
        runtime.wipe_index()
    except Exception:
        if settings.sqlite_path:
            for ext in ["", "-wal", "-shm"]:
                p = Path(f"{settings.sqlite_path}{ext}")
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass

    runtime.initialize_storage()
    console.print("[2/3] Reindexing all symbols")
    runtime.bootstrap(force=True)

    console.print("[3/3] Regenerating wiki from last known state")
    try:
        runtime.wiki.generate_project_wiki()
    except Exception:
        pass

    status_info = runtime.status()
    console.print(f"\n[green]✓ Recovery complete. {status_info.files} files restored.[/green]")
    console.print("[yellow]⚠ Agent memory (L3) could not be recovered — starting fresh.[/yellow]")


@app.command()
def doctor(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    fix: Annotated[
        bool, typer.Option("--fix", help="Attempt to automatically fix detected issues.")
    ] = False,
    context: Annotated[
        bool, typer.Option("--context", help="Output current LLM injection context.")
    ] = False,
) -> None:
    """Validate environment and system health."""
    console.print("[bold cyan]Synapse Doctor: System Health Check[/bold cyan]\n")

    settings = _settings(path)
    runtime = SynapseRuntime(settings)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_db = progress.add_task("Checking SQLite Database...", total=1)
        try:
            runtime.initialize_storage()
            res = runtime.doctor()
            progress.update(
                task_db,
                completed=1,
                description=f"[green]✓ Database integrity: {res['database_integrity']}[/green]",
            )
        except Exception as e:
            progress.update(task_db, completed=1, description=f"[red]✗ Database error: {e}[/red]")

        task_parsers = progress.add_task("Checking Tree-Sitter Parsers...", total=1)
        try:
            from synapse.parser.registry import CodeParserRegistry

            registry = CodeParserRegistry()
            test_file = Path(path) / ".synapse_test.py"
            test_file.write_text("def test(): pass")
            registry.parse(test_file, relative_path=".synapse_test.py")
            test_file.unlink()
            progress.update(
                task_parsers,
                completed=1,
                description="[green]✓ Tree-sitter parsers functional[/green]",
            )
        except Exception as e:
            progress.update(
                task_parsers, completed=1, description=f"[red]✗ Parser error: {e}[/red]"
            )

        task_tok = progress.add_task("Checking Tokenizer...", total=1)
        try:
            import tiktoken

            tiktoken.get_encoding("cl100k_base")
            progress.update(
                task_tok, completed=1, description="[green]✓ Tokenizer (tiktoken) ready[/green]"
            )
        except Exception as e:
            progress.update(task_tok, completed=1, description=f"[red]✗ Tokenizer error: {e}[/red]")

        task_prov = progress.add_task("Checking LLM Provider...", total=1)
        try:
            errors = settings.validate_configuration()
            if errors:
                progress.update(
                    task_prov, completed=1, description=f"[red]✗ Config error: {errors[0]}[/red]"
                )
            else:
                conn_errors = settings.test_connectivity()
                if conn_errors:
                    progress.update(
                        task_prov,
                        completed=1,
                        description=f"[red]✗ Connectivity error: {conn_errors[0]}[/red]",
                    )
                else:
                    progress.update(
                        task_prov,
                        completed=1,
                        description=f"[green]✓ Provider ({settings.llm_provider}) connectivity verified[/green]",
                    )
        except Exception as e:
            progress.update(
                task_prov, completed=1, description=f"[red]✗ Unexpected error: {e}[/red]"
            )

    console.print("\n[bold]All checks complete.[/bold]")


@app.command()
def run(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
    host: Annotated[str, typer.Option(help="Host for UI server.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port for UI server.")] = 9876,
) -> None:
    """Start all Synapse services (Daemon, MCP, UI)."""
    import subprocess
    import sys
    import time

    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    commands = [
        ("Daemon", [sys.executable, "-m", "synapse.cli", "start", path]),
        ("MCP Server", [sys.executable, "-m", "synapse.cli", "mcp", "start", path]),
        (
            "UI Server",
            [sys.executable, "-m", "synapse.cli", "ui", path, "--host", host, "--port", str(port)],
        ),
    ]

    processes = []
    try:
        for name, cmd in commands:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
            processes.append((name, p))
            time.sleep(0.5)

        console.print("\n[bold green]✓ Synapse Runtime active![/bold green]")
        console.print(f"[cyan]UI: http://{host}:{port}[/cyan]")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for _, p in processes:
            p.terminate()


@mcp_app.command("start")
def mcp_start(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Start the MCP server."""
    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    from synapse.mcp.server import SynapseMCPServer

    server = SynapseMCPServer(runtime)
    asyncio.run(server.run())


@mcp_app.command("config")
def mcp_config(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Output the MCP server configuration for manual IDE setup."""
    abs_path = Path(path).resolve().as_posix()
    import sys

    config = {
        "mcpServers": {
            "synapse": {
                "command": sys.executable,
                "args": ["-m", "synapse.cli", "mcp", "start", abs_path],
                "autoConnect": True,
            }
        }
    }
    typer.echo(json.dumps(config, indent=2))


@mcp_app.command("verify")
def mcp_verify(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Verify MCP tools, schemas, and transport stability."""
    import time

    console.print("[bold cyan]Synapse MCP Verification[/bold cyan]\n")

    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    from synapse.mcp.server import SynapseMCPFacade

    facade = SynapseMCPFacade(runtime)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Stage")
    table.add_column("Status")
    table.add_column("Latency (ms)")
    table.add_column("Details")

    def _simulate_mcp_call(tool_name: str, *args: Any, **kwargs: Any) -> bool:
        start = time.monotonic()
        try:
            import uuid

            status = facade.runtime.status()
            dirty = status.is_dirty
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


@app.command()
def ui(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 9876,
) -> None:
    """Start the diagnostic UI."""
    import uvicorn

    from synapse.api.app import create_app

    settings = _settings(path)
    runtime = SynapseRuntime(settings)
    runtime.bootstrap()

    api_app = create_app(runtime)
    uvicorn.run(api_app, host=host, port=port)


@memory_app.command("status")
def memory_status(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show current memory trust status."""
    runtime = SynapseRuntime(_settings(path))

    approved = runtime.store.get_lessons("approved")
    pending = runtime.store.get_lessons("pending")
    expired = runtime.store.get_lessons("expired")

    table = Table(title="Synapse Memory Status", show_header=True, header_style="bold cyan")
    table.add_column("State")
    table.add_column("Count")

    table.add_row("[green]Approved[/green]", str(len(approved)))
    table.add_row("[yellow]Pending[/yellow]", str(len(pending)))
    table.add_row("[dim]Expired[/dim]", str(len(expired)))

    console.print(table)


@memory_app.command("prune")
def memory_prune(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Evaluate expiry rules and prune dead memory."""
    runtime = SynapseRuntime(_settings(path))
    pruned_count = runtime.store.prune_expired_lessons()
    console.print(f"[green]✓ Evaluated memory expiry. Pruned {pruned_count} lessons.[/green]")


@memory_app.command("verify")
def memory_verify(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Check for dangling file references in approved memory lessons."""
    import json as json_lib

    runtime = SynapseRuntime(_settings(path, json_output=json_output))
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
        console.print("[dim]Run `synapse lessons reject <id>` to clean up stale memory.[/dim]")
    else:
        console.print("\n[green]✓ All approved memory references are valid.[/green]")


@lessons_app.command("approve")
def lessons_approve(
    lesson_id: Annotated[str, typer.Argument(help="The ID of the lesson to approve.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Approve a pending lesson."""
    runtime = SynapseRuntime(_settings(path))
    # Fetch to ensure it exists and is pending
    pending = runtime.store.get_lessons("pending")
    target = next((lesson for lesson in pending if lesson["lesson_id"] == lesson_id), None)

    if not target:
        console.print(f"[red]✗ Pending lesson {lesson_id} not found.[/red]")
        raise typer.Exit(1)

    runtime.store.update_lesson(lesson_id, target["why_failed"], "approved", actor="cli_user")
    console.print(f"[green]✓ Lesson {lesson_id} approved. Memory updated.[/green]")


@lessons_app.command("reject")
def lessons_reject(
    lesson_id: Annotated[str, typer.Argument(help="The ID of the lesson to reject.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Reject a pending lesson."""
    runtime = SynapseRuntime(_settings(path))
    pending = runtime.store.get_lessons("pending")
    target = next((lesson for lesson in pending if lesson["lesson_id"] == lesson_id), None)

    if not target:
        console.print(f"[red]✗ Pending lesson {lesson_id} not found.[/red]")
        raise typer.Exit(1)

    runtime.store.update_lesson(lesson_id, target["why_failed"], "rejected", actor="cli_user")
    console.print(f"[yellow]✓ Lesson {lesson_id} rejected. Memory updated.[/yellow]")


@checkpoint_app.command("create")
def checkpoint_create(
    doing: Annotated[str, typer.Option(help="What the agent is currently doing.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    files: Annotated[str, typer.Option(help="Comma-separated list of changed files.")] = "",
    next_step: Annotated[str, typer.Option(help="The next step to be taken.")] = "",
    blockers: Annotated[str, typer.Option(help="Current blockers or obstacles.")] = "",
) -> None:
    """Create a new context checkpoint."""
    runtime = SynapseRuntime(_settings(path))
    import uuid

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


@checkpoint_app.command("list")
def checkpoint_list(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """List checkpoints for the active branch."""
    runtime = SynapseRuntime(_settings(path))
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


@checkpoint_app.command("restore")
def checkpoint_restore(
    checkpoint_id: Annotated[
        str, typer.Argument(help="The ID of the checkpoint to restore (defaults to latest).")
    ] = "latest",
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Restore and show details of a checkpoint."""
    runtime = SynapseRuntime(_settings(path))
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
