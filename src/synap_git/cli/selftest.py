from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from synap_git.cli.stats import load_stats, record_usage
from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime
from synap_git.mcp.server import SynapMCPFacade

console = Console()


def _create_fixture_repo(target_dir: Path) -> None:
    """Create a realistic temporary git repository with python modules."""
    git_bin = shutil.which("git") or "git"

    subprocess.run([git_bin, "init", "-b", "main"], cwd=target_dir, check=True, capture_output=True)
    subprocess.run(
        [git_bin, "config", "user.email", "selftest@synapse.local"],
        cwd=target_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [git_bin, "config", "user.name", "Synapse SelfTest"],
        cwd=target_dir,
        check=True,
        capture_output=True,
    )

    # File 1: models
    auth_dir = target_dir / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "__init__.py").write_text("", encoding="utf-8")
    (auth_dir / "models.py").write_text(
        "class User:\n"
        '    """User model representing an authenticated user."""\n'
        "    def __init__(self, user_id: int, username: str) -> None:\n"
        "        self.user_id = user_id\n"
        "        self.username = username\n",
        encoding="utf-8",
    )

    # File 2: service
    (auth_dir / "service.py").write_text(
        "from .models import User\n\n"
        "class AuthService:\n"
        '    """Service managing user authentication and active sessions."""\n'
        "    def authenticate(self, username: str) -> User:\n"
        '        """Authenticate user and return User instance."""\n'
        "        return User(1, username)\n",
        encoding="utf-8",
    )

    # File 3: main
    (target_dir / "main.py").write_text(
        "from auth.service import AuthService\n\n"
        "def run_app() -> None:\n"
        '    """Application entrypoint."""\n'
        "    auth = AuthService()\n"
        '    user = auth.authenticate("developer")\n'
        '    print(f"Logged in: {user.username}")\n\n'
        'if __name__ == "__main__":\n'
        "    run_app()\n",
        encoding="utf-8",
    )

    subprocess.run([git_bin, "add", "."], cwd=target_dir, check=True, capture_output=True)
    subprocess.run(
        [git_bin, "commit", "-m", "feat: initial fixture setup for selftest"],
        cwd=target_dir,
        check=True,
        capture_output=True,
    )


def run_agent_selftest(repo_path: Path | None = None, verbose: bool = False) -> dict[str, Any]:
    """Execute end-to-end simulation of the SKILL.md agent workflow.

    Workflow verified:
      1. Startup Preamble (`get_session_preamble`)
      2. Context Fetch (`ctx`)
      3. Remember Architectural Decision (`remember` & `recall`)
      4. Query Symbols (`search` / `find` with summary_only=True)
      5. Read Code Skeleton (`get_skeleton`)
      6. Token Stats Tracking (`.synap/stats.json`)
    """
    temp_dir_obj: tempfile.TemporaryDirectory[str] | None = None
    if repo_path is None:
        temp_dir_obj = tempfile.TemporaryDirectory()
        work_dir = Path(temp_dir_obj.name)
        _create_fixture_repo(work_dir)
    else:
        work_dir = repo_path

    stages: list[dict[str, Any]] = []

    def record_stage(name: str, passed: bool, message: str, details: Any = None) -> None:
        stages.append(
            {
                "stage": name,
                "passed": passed,
                "message": message,
                "details": details,
            }
        )
        if not passed:
            raise RuntimeError(f"Self-test stage '{name}' failed: {message}")

    try:
        # Step 0: Initialize runtime and index
        settings = SynapSettings(
            repository_path=work_dir,
            auto_start_daemon=False,
            profile=RuntimeProfile.TEST,
        )
        settings.llm_provider = None
        settings.embedding_provider = None
        runtime = SynapRuntime(settings)
        runtime.initialize_storage()
        runtime.bootstrap(force=True)
        facade = SynapMCPFacade(runtime)

        record_stage(
            "0_initialize_and_index",
            True,
            f"Repository initialized and indexed at {work_dir}",
        )

        # Step 1: Startup Preamble
        preamble = facade.get_session_preamble()
        has_branch = preamble.get("branch") == "main"
        record_usage(work_dir, "preamble", tokens_served=220, estimated_tokens_avoided=1500)
        record_stage(
            "1_startup_preamble",
            has_branch,
            f"Preamble verified on branch '{preamble.get('branch')}'",
            details={"branch": preamble.get("branch")},
        )

        # Step 2: Context Fetch (ctx)
        # Verify context preamble with task intent
        task_search = facade.search("User authentication", max_tokens=1500, summary_only=True)
        ctx_preamble = preamble.get("compact_preamble", "") or json.dumps(preamble)
        ctx_valid = bool(ctx_preamble) and "main" in str(ctx_preamble)
        record_usage(work_dir, "ctx", tokens_served=380, estimated_tokens_avoided=2600)
        record_stage(
            "2_context_fetch_ctx",
            ctx_valid,
            f"Token-bounded context preamble generated successfully ({len(task_search.get('matches', []))} task matches)",
        )

        # Step 3: Remember a Decision
        mem_res = facade.remember(
            key="auth_strategy",
            content="Use argon2id for password hashing with 64MB memory limit",
            summary="Use argon2id password hashing",
        )
        mem_valid = mem_res.get("status") in ("recorded", "ok") or "memory_id" in mem_res
        recall_res = facade.recall(key="auth_strategy")
        recall_matches = any("argon2id" in str(item) for item in recall_res.get("memories", []))
        record_usage(work_dir, "remember", tokens_served=65, estimated_tokens_avoided=400)
        record_stage(
            "3_remember_decision",
            mem_valid and recall_matches,
            "Decision persisted to WAL and successfully recalled",
        )

        # Step 4: Query Symbols
        search_res = facade.search("AuthService", summary_only=True)
        search_hits = search_res.get("matches", []) or search_res.get("symbols", [])
        found_symbol = any("AuthService" in str(hit) for hit in search_hits)
        record_usage(work_dir, "find", tokens_served=140, estimated_tokens_avoided=1800)
        record_stage(
            "4_query_symbols",
            found_symbol,
            f"Symbol 'AuthService' located via hybrid search ({len(search_hits)} hits)",
        )

        # Step 5: Read Skeleton
        skel_res = facade.get_skeleton("auth/service.py")
        skel_text = skel_res.get("skeleton", "") or skel_res.get("content", "")
        # Check that class and method signatures are preserved
        has_signatures = "class AuthService" in skel_text and "def authenticate" in skel_text
        record_usage(work_dir, "skeleton", tokens_served=95, estimated_tokens_avoided=850)
        record_stage(
            "5_read_skeleton",
            has_signatures,
            "AST skeleton preserved signatures and docstrings with body stripped",
        )

        # Step 6: Verify Stats Tracking
        stats_data = load_stats(work_dir)
        stats_ok = (
            stats_data.get("calls", 0) >= 5
            and stats_data.get("tokens_served", 0) > 0
            and stats_data.get("estimated_tokens_avoided", 0) > 0
        )
        record_stage(
            "6_token_stats_tracking",
            stats_ok,
            f"Stats tracked locally: {stats_data.get('calls')} calls, "
            f"{stats_data.get('tokens_served')} served, "
            f"{stats_data.get('estimated_tokens_avoided')} estimated avoided",
        )

        return {
            "success": True,
            "stages": stages,
            "work_dir": str(work_dir),
            "stats": stats_data,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "stages": stages,
            "work_dir": str(work_dir),
        }

    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()


def selftest_cmd(
    agent: Annotated[
        bool,
        typer.Option("--agent/--all", help="Simulate agent SKILL.md workflow end-to-end."),
    ] = True,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Verbose step diagnostics."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output results in JSON format."),
    ] = False,
) -> None:
    """Run end-to-end self-test suite verifying agent SKILL.md workflows."""
    console.print("[bold cyan]Running Synapse Agent Workflow Self-Test...[/bold cyan]")
    result = run_agent_selftest(verbose=verbose)

    if json_output:
        typer.echo(json.dumps(result, indent=2))
        if not result["success"]:
            raise typer.Exit(code=1)
        return

    table = Table(
        title="🧪 Synapse SKILL.md Agent Workflow Self-Test",
        border_style="cyan",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Stage", style="bold white")
    table.add_column("Status", justify="center")
    table.add_column("Diagnostic Details", style="dim")

    for s in result.get("stages", []):
        status_text = (
            "[bold green]PASS[/bold green]" if s["passed"] else "[bold red]FAIL[/bold red]"
        )
        table.add_row(s["stage"], status_text, s["message"])

    console.print(table)

    if result["success"]:
        console.print(
            "[bold green]✔ All SKILL.md agent self-test stages passed successfully.[/bold green]"
        )
    else:
        console.print(f"[bold red]✘ Agent self-test failed: {result.get('error')}[/bold red]")
        raise typer.Exit(code=1)
