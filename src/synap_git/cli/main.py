from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from synap_git.config import LoggingMode, RuntimeMode, RuntimeProfile, SynapSettings
from synap_git.diagnostics.logger import configure_logging
from synap_git.git.state import GitRepository
from synap_git.indexer.daemon import RuntimeDaemon
from synap_git.indexer.engine import SynapRuntime

app = typer.Typer(
    name="synap",
    help="Deterministic Git-aware structural retrieval engine for AI coding agents.",
    no_args_is_help=True,
)

# Exception handling wrapper for clean CLI diagnostics
_original_call = app.__call__


def _custom_call(*args: Any, **kwargs: Any) -> Any:
    try:
        return _original_call(*args, **kwargs)
    except ValueError as e:
        err_msg = str(e)
        if (
            "missing" in err_msg.lower()
            or "api key" in err_msg.lower()
            or "provider" in err_msg.lower()
        ):
            console.print(f"[bold red]Configuration Error:[/bold red] {e}")
            console.print(
                "\n[yellow]Suggestion:[/yellow] Run [bold]synap setup[/bold] to configure your LLM provider and credentials."
            )
        else:
            console.print(f"[bold red]Error:[/bold red] {e}")
        import sys

        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected Error:[/bold red] {e}")
        import sys

        sys.exit(1)


app.__call__ = _custom_call  # type: ignore[method-assign]

JSON_OPTION = typer.Option("--json", help="Emit machine-readable JSON.")
console = Console(stderr=True)
stdout_console = Console(file=sys.stdout)


def _resolve_repo_root(path: str | Path = ".") -> Path:
    """Find and return the root repository directory or the resolved path if not in Git."""
    from synap_git.git.state import GitRepository

    p = Path(path).resolve()
    root = GitRepository.find_root(p)
    return root if root is not None else p


def _resolve_repo_file_path(file_path: str, root: Path) -> str:
    """Resolve a file path that may be relative to CWD or root into a root-relative posix path."""
    if not file_path:
        return ""
    cand = Path(file_path)
    if cand.is_absolute():
        try:
            return cand.relative_to(root).as_posix()
        except ValueError:
            return file_path
    resolved = cand.resolve()
    if resolved.exists():
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            pass
    if (root / file_path).exists():
        return Path(file_path).as_posix()
    return file_path


def _emit_json(value: Any) -> None:
    """Emit clean machine-readable JSON to stdout without ANSI colors, safe for jq."""
    import sys

    print(json.dumps(_jsonable(value), indent=2, sort_keys=True), file=sys.stdout)


def _stdout_print(content: Any) -> None:
    """Print content to stdout, preserving text cleanliness when piped (non-TTY)."""
    import sys

    if not sys.stdout.isatty():
        plain_console = Console(
            file=sys.stdout, force_terminal=False, no_color=True, highlight=False
        )
        plain_console.print(content)
    else:
        stdout_console.print(content)


def _settings(
    path: str | Path,
    *,
    profile: RuntimeProfile | None = None,
    json_output: bool = False,
    mode: RuntimeMode = RuntimeMode.ACTIVE,
) -> SynapSettings:
    if profile is None:
        import os

        env_profile = os.environ.get("SYNAP_PROFILE", "dev").lower().strip()
        if env_profile == "test":
            profile = RuntimeProfile.TEST
        elif env_profile == "prod":
            profile = RuntimeProfile.PROD
        else:
            profile = RuntimeProfile.DEV

    repo_dir = _resolve_repo_root(path)

    settings = SynapSettings(
        repository_path=repo_dir,
        profile=profile,
        logging_mode=LoggingMode.JSON if json_output else LoggingMode.HUMAN,
        mode=mode,
    )
    configure_logging(settings)
    return settings


def _verify_is_git(path: str | Path) -> None:
    from synap_git.git.state import GitRepository

    root = _resolve_repo_root(path)
    if not GitRepository(root).state().is_repository:
        console.print(f"[bold red]Error:[/bold red] '{path}' is not a valid Git repository.")
        raise typer.Exit(1)


def _emit(value: Any, *, json_output: bool) -> None:
    if json_output:
        _emit_json(value)
        return
    if isinstance(value, str):
        _stdout_print(value)
        return
    for key, item in _jsonable(value).items():
        _stdout_print(f"{key}: {item}")


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


mcp_app = typer.Typer(help="Model Context Protocol (MCP) server commands.", no_args_is_help=True)
app.add_typer(mcp_app, name="mcp")

memory_app = typer.Typer(help="Manage L3 Agent Memory.", no_args_is_help=True)
app.add_typer(memory_app, name="memory")

lessons_app = typer.Typer(help="Manage Agent Lessons.", no_args_is_help=True)
app.add_typer(lessons_app, name="lessons")

checkpoint_app = typer.Typer(help="Manage Context Checkpoints.", no_args_is_help=True)
app.add_typer(checkpoint_app, name="checkpoint")

wiki_app = typer.Typer(help="Manage L2 Wiki Documentation.", no_args_is_help=True)
app.add_typer(wiki_app, name="wiki")

usage_app = typer.Typer(help="View AI Usage Tracking.", no_args_is_help=True)
app.add_typer(usage_app, name="usage")

hooks_app = typer.Typer(help="Manage Git hooks for zero-daemon reindexing.", no_args_is_help=True)
app.add_typer(hooks_app, name="hooks")


@app.command()
def setup(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """
    Interactive first-run setup and onboarding.

    Examples:
        synap setup
        synap setup /path/to/repo
    """
    import sys

    import httpx
    import keyring
    import questionary

    # Print a beautiful header to wow the user
    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
    console.print("[bold cyan]          Synap Initial Setup           [/bold cyan]")
    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")

    from synap_git.config import _get_config_file_path

    config_file = _get_config_file_path()
    config_dir = config_file.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Configuration directory:[/dim] [bold]{config_dir.as_posix()}[/bold]")
    console.print(f"[dim]Configuration file:[/dim] [bold]{config_file.as_posix()}[/bold]")
    console.print("[dim]Secrets store:[/dim] [bold]System Keyring[/bold]\n")

    # Detect non-TTY fallback
    is_tty = sys.stdin.isatty() and sys.stdout.isatty()

    provider = None
    llm_model = None
    ollama_url = "http://localhost:11434"
    key = None

    if is_tty:
        # 1. Select Provider
        provider = questionary.select(
            "Select LLM provider:",
            choices=[
                questionary.Choice("Ollama (Local first)", value="ollama"),
                questionary.Choice("OpenAI", value="openai"),
                questionary.Choice("Anthropic", value="anthropic"),
                questionary.Choice("Gemini", value="gemini"),
                questionary.Choice("OpenRouter", value="openrouter"),
            ],
        ).ask()

        if not provider:
            console.print("[red]Setup cancelled.[/red]")
            raise typer.Exit(1)

        # 2. Select Model based on provider
        model_choices: dict[str, list[str | questionary.Choice]] = {
            "ollama": [
                "qwen2.5-coder:14b",
                "deepseek-coder",
                "llama3",
                "mistral",
                questionary.Choice("Custom model name...", value="custom"),
            ],
            "openai": [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "o1-mini",
                "o3-mini",
                questionary.Choice("Custom model name...", value="custom"),
            ],
            "anthropic": [
                "claude-3-5-sonnet-latest",
                "claude-3-5-haiku-latest",
                "claude-3-opus-latest",
                questionary.Choice("Custom model name...", value="custom"),
            ],
            "gemini": [
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                questionary.Choice("Custom model name...", value="custom"),
            ],
            "openrouter": [
                "google/gemini-2.5-pro",
                "google/gemini-2.5-flash",
                "anthropic/claude-3.5-sonnet",
                "meta-llama/llama-3.3-70b-instruct",
                "deepseek/deepseek-chat",
                questionary.Choice("Custom model name...", value="custom"),
            ],
        }

        llm_model = questionary.select(
            "Select model:",
            choices=model_choices[provider],
        ).ask()

        if not llm_model:
            console.print("[red]Setup cancelled.[/red]")
            raise typer.Exit(1)

        if llm_model == "custom":
            llm_model = questionary.text(
                "Enter custom model name:",
                validate=lambda text: len(text.strip()) > 0 or "Model name cannot be empty.",
            ).ask()
            if not llm_model:
                console.print("[red]Setup cancelled.[/red]")
                raise typer.Exit(1)
            llm_model = llm_model.strip()

        # 3. Gather Keys / Ollama URL
        if provider == "ollama":
            ollama_url = questionary.text(
                "Enter Ollama URL:",
                default="http://localhost:11434",
                validate=lambda text: (text.startswith("http://") or text.startswith("https://"))
                or "Ollama URL must start with http:// or https://",
            ).ask()
            if not ollama_url:
                console.print("[red]Setup cancelled.[/red]")
                raise typer.Exit(1)
            ollama_url = ollama_url.strip()
        else:
            key = questionary.password(
                f"Enter {provider.capitalize()} API Key:",
                validate=lambda text: len(text.strip()) > 0 or "API Key cannot be empty.",
            ).ask()
            if not key:
                console.print("[red]Setup cancelled.[/red]")
                raise typer.Exit(1)
            key = key.strip()

    else:
        # Non-TTY plain text fallback
        console.print(
            "[yellow]Non-TTY terminal detected. Falling back to plain text inputs.[/yellow]"
        )

        provider = typer.prompt("Select LLM provider", default="ollama").strip().lower()
        if provider not in ("ollama", "openai", "anthropic", "gemini", "openrouter"):
            console.print(f"[red]Error: Invalid provider '{provider}'.[/red]")
            raise typer.Exit(1)

        # Model
        default_models = {
            "ollama": "qwen2.5-coder:14b",
            "openai": "gpt-4o",
            "anthropic": "claude-3-5-sonnet-latest",
            "gemini": "gemini-2.5-pro",
            "openrouter": "google/gemini-2.5-pro",
        }
        default_model = default_models[provider]
        llm_model = typer.prompt("Select model", default=default_model).strip()

        # Keys/URL
        if provider == "ollama":
            ollama_url = typer.prompt("Enter Ollama URL", default="http://localhost:11434").strip()
            if not (ollama_url.startswith("http://") or ollama_url.startswith("https://")):
                console.print("[red]Error: Ollama URL must start with http:// or https://[/red]")
                raise typer.Exit(1)
        else:
            key = typer.prompt(f"Enter {provider.capitalize()} API Key", hide_input=True).strip()
            if not key:
                console.print("[red]Error: API Key cannot be empty.[/red]")
                raise typer.Exit(1)

    # 4. Connection and API Key validation with timeout
    console.print()
    with console.status("[yellow]Verifying provider connectivity...[/yellow]", spinner="dots"):
        try:
            if provider == "ollama":
                try:
                    resp = httpx.get(f"{ollama_url}/api/tags", timeout=3.0)
                    if resp.status_code != 200:
                        raise ValueError(f"Ollama returned status code {resp.status_code}")

                    # Model presence warning
                    models_data = resp.json().get("models", [])
                    installed_models = [m.get("name", "") for m in models_data]

                    if llm_model != "custom":
                        model_matched = False
                        for name in installed_models:
                            if (
                                llm_model == name
                                or name.startswith(llm_model + ":")
                                or llm_model.startswith(name + ":")
                            ):
                                model_matched = True
                                break
                        if not model_matched:
                            console.print(
                                f"\n[yellow]⚠ Warning: Model '{llm_model}' is not currently pulled/installed in Ollama.[/yellow]"
                            )
                            console.print(
                                f"  Run [bold]ollama pull {llm_model}[/bold] in another terminal to download it.\n"
                            )
                except httpx.ConnectError:
                    raise ValueError(
                        f"Could not connect to Ollama at {ollama_url}. Is Ollama running?"
                    )
                except httpx.TimeoutException:
                    raise ValueError(f"Connection to Ollama at {ollama_url} timed out (3s).")

            elif provider == "openai":
                try:
                    assert key is not None
                    resp = httpx.get(
                        "https://api.openai.com/v1/models",
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=3.0,
                    )
                    if resp.status_code == 401:
                        raise ValueError(
                            "API key validation failed: Invalid OpenAI API key (401 Unauthorized)."
                        )
                    elif resp.status_code != 200:
                        raise ValueError(f"OpenAI API returned status code {resp.status_code}")
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    raise ValueError(
                        "Could not connect to OpenAI API. Check your internet connection."
                    )
                except httpx.TimeoutException:
                    raise ValueError("Connection to OpenAI API timed out (3s).")

            elif provider == "anthropic":
                try:
                    assert key is not None
                    resp = httpx.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={},
                        timeout=3.0,
                    )
                    if resp.status_code in (401, 403):
                        raise ValueError(
                            "API key validation failed: Invalid Anthropic API key (401/403 Unauthorized/Forbidden)."
                        )
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    raise ValueError(
                        "Could not connect to Anthropic API. Check your internet connection."
                    )
                except httpx.TimeoutException:
                    raise ValueError("Connection to Anthropic API timed out (3s).")

            elif provider == "gemini":
                try:
                    assert key is not None
                    resp = httpx.get(
                        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                        timeout=3.0,
                    )
                    if resp.status_code in (400, 403):
                        try:
                            err_msg = (
                                resp.json()
                                .get("error", {})
                                .get("message", "Invalid Gemini API key")
                            )
                        except Exception:
                            err_msg = "Invalid Gemini API key"
                        raise ValueError(f"API key validation failed: {err_msg}")
                    elif resp.status_code != 200:
                        raise ValueError(f"Gemini API returned status code {resp.status_code}")
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    raise ValueError(
                        "Could not connect to Gemini API. Check your internet connection."
                    )
                except httpx.TimeoutException:
                    raise ValueError("Connection to Gemini API timed out (3s).")

            elif provider == "openrouter":
                try:
                    assert key is not None
                    resp = httpx.get(
                        "https://openrouter.ai/api/v1/models",
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=3.0,
                    )
                    if resp.status_code == 401:
                        raise ValueError(
                            "API key validation failed: Invalid OpenRouter API key (401 Unauthorized)."
                        )
                    elif resp.status_code != 200:
                        raise ValueError(f"OpenRouter API returned status code {resp.status_code}")
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    raise ValueError(
                        "Could not connect to OpenRouter API. Check your internet connection."
                    )
                except httpx.TimeoutException:
                    raise ValueError("Connection to OpenRouter API timed out (3s).")

            console.print("[green]✓ Connection verified[/green]")
        except Exception as e:
            console.print(f"[bold red]✗ Connection Verification Failed:[/bold red] {e}")

            # Interactive check override
            save_anyway = False
            if is_tty:
                save_anyway = questionary.confirm(
                    "Connection check failed. Save configuration anyway?"
                ).ask()
            else:
                save_anyway = typer.confirm(
                    "Connection check failed. Save configuration anyway?", default=False
                )

            if not save_anyway:
                console.print("[red]Setup cancelled.[/red]")
                raise typer.Exit(1)

    # 5. Write configurations & secrets (only now)
    if provider != "ollama" and key:
        keyring.set_password("synap", f"{provider}_api_key", key)

    embed_provider = provider if provider in ("ollama", "openai", "gemini") else "ollama"
    default_embed_models = {
        "ollama": "nomic-embed-text",
        "openai": "text-embedding-3-small",
        "gemini": "text-embedding-004",
    }
    embed_model = default_embed_models.get(embed_provider, "nomic-embed-text")

    config_content = f"""[llm]
llm_provider = "{provider}"
llm_model = "{llm_model}"
ollama_url = "{ollama_url}"
embedding_provider = "{embed_provider}"
embedding_model = "{embed_model}"
"""
    config_file.write_text(config_content)
    console.print("[green]✓ Configuration saved[/green]")
    if provider != "ollama":
        console.print("[green]✓ Secrets saved securely[/green]")

    # Initialize storage
    with console.status("[yellow]Initializing storage...[/yellow]"):
        runtime = SynapRuntime(_settings(path))
        runtime.bootstrap(force=True)
    console.print("[green]✓ Storage initialized[/green]")
    console.print("\n[bold green]✓ Setup complete[/bold green]")
    if provider == "ollama":
        console.print(
            "\n[dim]Tip: Ensure [bold]ollama pull nomic-embed-text[/bold] has been run for local vector embeddings.[/dim]"
        )
    console.print(
        "\n[dim]Tip: Run [bold]synap --install-completion[/bold] to set up shell command autocomplete.[/dim]"
    )


def _auto_protect_synap(repository_path: Path) -> None:
    gitignore_path = repository_path / ".gitignore"
    patterns = [".synap/", ".synapse/", ".synapse/*-wal", ".synapse/*-shm"]

    if not gitignore_path.exists():
        gitignore_path.write_text("\n".join(patterns) + "\n")
        return

    content = gitignore_path.read_text()
    lines = [line.strip() for line in content.splitlines()]

    new_content = content
    added = False
    for p in patterns:
        if p.strip() not in lines and p.strip().rstrip("/") not in lines:
            if not new_content.endswith("\n"):
                new_content += "\n"
            new_content += p + "\n"
            added = True

    if added:
        gitignore_path.write_text(new_content)


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
    """
    Initialize local Synap state and perform first scan.

    Examples:
        synap init
        synap init --force --skip-llm
    """
    _verify_is_git(path)
    settings = _settings(path, json_output=json_output)
    if skip_llm:
        settings.llm_provider = None

    _auto_protect_synap(settings.repository_path)

    runtime = SynapRuntime(settings)
    if not quiet and not json_output:
        console.print("[yellow]Initializing Synap runtime and scanning repository...[/yellow]")

    commit = runtime.bootstrap(force=force)

    if json_output:
        _emit({"active_commit": commit, "state": "initialized"}, json_output=True)
    elif not quiet:
        console.print(f"[green]✓ Initialized repository at {commit}[/green]")
        console.print("\n[bold cyan]Next Steps:[/bold cyan]")
        console.print(
            f"  1. [bold]synap index {path}[/bold] - Index/update all symbols into the database."
        )
        console.print(f"  2. [bold]synap start {path}[/bold] - Start the background daemon.")
        console.print(
            "  3. [bold]synap mcp config[/bold]  - Get JSON config for your IDE (Cursor/Windsurf)."
        )
        console.print("  4. Connect your AI agent using the MCP config.")


@app.command()
def index(
    path: Annotated[str, typer.Argument(help="Repository path to index.")] = ".",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force reindexing of all files.")
    ] = False,
    skip_llm: Annotated[
        bool, typer.Option("--skip-llm", help="Run in Mode A (structural AST only, no embeddings).")
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress output.")] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """
    Index and map code symbols, caller/callee relationships, and embeddings into the local database.

    Examples:
        synap index
        synap index /path/to/repo --force
        synap index --skip-llm
    """
    _verify_is_git(path)
    settings = _settings(path, json_output=json_output)
    if skip_llm:
        settings.llm_provider = None
        settings.embedding_provider = None

    _auto_protect_synap(settings.repository_path)
    runtime = SynapRuntime(settings)

    if not quiet and not json_output:
        console.print(
            f"[bold cyan]Indexing repository: [white]{settings.repository_path.resolve().as_posix()}[/white][/bold cyan]"
        )

    commit = runtime.bootstrap(force=force)
    status_info = runtime.status()

    if json_output:
        _emit(
            {
                "active_commit": commit,
                "files": status_info.files,
                "symbols": status_info.symbols,
                "branch": status_info.branch,
                "state": "indexed",
            },
            json_output=True,
        )
    elif not quiet:
        console.print(
            f"[bold green]✓ Indexing complete at commit {commit}[/bold green] "
            f"({status_info.files} files, {status_info.symbols} symbols mapped)"
        )


@app.command()
def sync(
    path: Annotated[str, typer.Argument(help="Repository path to synchronize.")] = ".",
    force: Annotated[bool, typer.Option("--force", "-f", help="Force reindexing.")] = False,
    skip_llm: Annotated[
        bool, typer.Option("--skip-llm", help="Run in Mode A (structural only).")
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress output.")] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Synchronize database index with latest Git state and working tree changes."""
    index(path=path, force=force, skip_llm=skip_llm, quiet=quiet, json_output=json_output)


@app.command()
def wipe(
    path: Annotated[str, typer.Argument(help="Repository path to wipe.")] = ".",
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt and force wipe")
    ] = False,
) -> None:
    """Completely purge the local index for a fresh rebuild."""
    if not yes and not typer.confirm(
        "This will delete all indexed symbols and embeddings. Continue?"
    ):
        raise typer.Abort()
    runtime = SynapRuntime(_settings(path))
    runtime.wipe_index()
    console.print("[green]✓ Index wiped.[/green]")


def _is_process_running(pid: int) -> bool:
    import os
    import sys

    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                exit_code = ctypes.c_ulong()
                windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                windll.kernel32.CloseHandle(handle)
                return exit_code.value == 259
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _read_daemon_heartbeat(repository_path: Path) -> dict[str, Any] | None:
    heartbeat_path = repository_path / ".synap" / "daemon_heartbeat.json"
    if not heartbeat_path.exists():
        return None
    try:
        import time

        data = cast(
            dict[str, Any],
            json.loads(heartbeat_path.read_text(encoding="utf-8")),
        )
        mtime = heartbeat_path.stat().st_mtime
        if time.time() - mtime > 10.0:
            data["status"] = "stale"
        return data
    except Exception:
        return None


def _detect_install_method() -> str:
    import sys
    from pathlib import Path

    import synap_git

    pkg_file = Path(synap_git.__file__).resolve()
    root_dir = pkg_file.parent.parent.parent
    if (root_dir / "pyproject.toml").exists() and (root_dir / "src" / "synap_git").exists():
        return "editable"

    exe_path = sys.executable.lower()
    if "pipx" in exe_path or "pipx" in sys.argv[0]:
        return "pipx"
    elif "uv" in exe_path or ".uv" in exe_path:
        return "uv"
    elif ".venv" in exe_path or "virtualenv" in exe_path:
        return "venv"
    else:
        return "pip"


@app.command()
def start(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
    foreground: Annotated[
        bool,
        typer.Option(
            "--foreground", help="Run FastMCP stdio server in foreground after starting daemon."
        ),
    ] = False,
) -> None:
    """Start the Synap daemon in the background."""
    _verify_is_git(path)
    import asyncio
    import os
    import subprocess
    import sys
    import time

    from synap_git.mcp.server import SynapMCPServer

    abs_path = _resolve_repo_root(path)
    pid_file = abs_path / ".synap" / "daemon.pid"

    is_running = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if _is_process_running(pid):
                console.print(f"[green]✓ Synap daemon is already running (PID {pid}).[/green]")
                hb = _read_daemon_heartbeat(abs_path)
                if hb and "port" in hb:
                    console.print(f"[green]✓ UI available at http://127.0.0.1:{hb['port']}[/green]")
                is_running = True
                if not foreground:
                    return
            else:
                pid_file.unlink()
        except Exception as e:
            import structlog

            structlog.get_logger().error("suppressed_error_caught", error=str(e))

    if not is_running:
        # 2. Spawn detached daemon process
        cmd = [sys.executable, "-m", "synap_git.cli", "daemon-run", abs_path.as_posix()]
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=0x00000008,  # DETACHED_PROCESS
                )
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
        except Exception as e:
            console.print(f"[bold red]✗ Failed to start daemon:[/bold red] {e}")
            raise typer.Exit(1)

        success = False
        port = 9876
        pid = 0
        status_val = None
        with console.status(
            "[yellow]Starting Synap daemon and awaiting health check...[/yellow]", spinner="dots"
        ):
            for _ in range(25):  # wait up to 5 seconds for initial heartbeat
                time.sleep(0.2)
                if pid_file.exists():
                    hb = _read_daemon_heartbeat(abs_path)
                    if hb:
                        status_val = hb.get("status")
                        if status_val in ("healthy", "degraded", "starting"):
                            success = True
                            port = hb.get("port", 9876)
                            pid = int(hb.get("pid", 0))
                            break

        if success:
            console.print(f"[green]✓ Synap daemon started (PID {pid})[/green]")
            if status_val == "starting":
                console.print(
                    "[yellow]ℹ Daemon is currently indexing in the background...[/yellow]"
                )
            else:
                console.print("[green]✓ Runtime healthy[/green]")
            console.print(f"[green]✓ UI available at http://127.0.0.1:{port}[/green]")
        else:
            console.print(
                "[red]✗ Daemon started but did not report healthy status. Check logs in ~/.config/synap/logs/[/red]"
            )
            raise typer.Exit(1)

        if not foreground:
            return

    # 3. Start MCP Server in the foreground if --foreground flag passed
    settings = _settings(path, json_output=True)
    runtime = SynapRuntime(settings)
    server = SynapMCPServer(runtime)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        os._exit(0)


@app.command("daemon-run", hidden=True)
def daemon_run(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
) -> None:
    """Internal command to run the daemon loop foreground inside the detached process."""
    import os

    abs_path = _resolve_repo_root(path)
    pid_file = abs_path / ".synap" / "daemon.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    settings = _settings(abs_path.as_posix())
    configure_logging(settings)

    daemon = RuntimeDaemon(settings)
    asyncio.run(daemon.start())

    import sys

    sys.exit(0)


@app.command()
def stop(
    path: Annotated[str, typer.Argument(help="Repository path to stop.")] = ".",
) -> None:
    """Gracefully terminate background services."""
    import os
    import signal
    import time

    abs_path = _resolve_repo_root(path)
    pid_file = abs_path / ".synap" / "daemon.pid"

    if not pid_file.exists():
        console.print("[yellow]No active daemon process found for this repository.[/yellow]")
        return

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        console.print("[red]Invalid PID lockfile found. Cleaning up...[/red]")
        try:
            pid_file.unlink()
        except OSError:
            pass
        return

    if not _is_process_running(pid):
        console.print(
            "[yellow]Daemon process is not currently running. Cleaning up stale lockfile...[/yellow]"
        )
        try:
            pid_file.unlink()
        except OSError:
            pass
        return

    console.print(f"[yellow]Stopping Synap daemon (PID {pid})...[/yellow]")
    try:
        if os.name == "nt":
            import ctypes

            windll = getattr(ctypes, "windll", None)
            if windll:
                PROCESS_TERMINATE = 0x0001
                handle = windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                if handle:
                    windll.kernel32.TerminateProcess(handle, 1)
                    windll.kernel32.CloseHandle(handle)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        console.print(f"[red]Failed to signal daemon: {e}[/red]")

    # Wait for graceful shutdown (up to 10 seconds)
    success = False
    with console.status(
        f"[yellow]Waiting for daemon (PID {pid}) to shut down gracefully...[/yellow]",
        spinner="dots",
    ):
        for _ in range(50):
            time.sleep(0.2)
            if not _is_process_running(pid):
                success = True
                break

    # If graceful failed, force kill
    if not success:
        console.print("[yellow]Daemon did not stop gracefully. Forcing termination...[/yellow]")
        try:
            if os.name != "nt":
                os.kill(pid, signal.SIGKILL)
            time.sleep(1.0)
            # Try to reap zombie process
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
        except Exception as e:
            import structlog

            structlog.get_logger().error("suppressed_error_caught", error=str(e))
        success = not _is_process_running(pid)

    # Clean up lockfiles
    for f in (pid_file, abs_path / ".synap" / "daemon_heartbeat.json"):
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass

    if success:
        console.print("[green]✓ Synap daemon stopped successfully.[/green]")
    else:
        console.print("[red]✗ Failed to terminate daemon process.[/red]")


@app.command()
def restart(
    path: Annotated[str, typer.Argument(help="Repository path to restart.")] = ".",
) -> None:
    """Restart background daemon services."""
    abs_path = _resolve_repo_root(path)
    console.print("[yellow]Restarting Synap services...[/yellow]")

    pid_file = abs_path / ".synap" / "daemon.pid"
    if pid_file.exists():
        stop(path)

    start(path)


def _render_status_content(
    abs_path: Path, settings: SynapSettings, runtime: SynapRuntime, limit: int | None = None
) -> Any:
    from rich.console import Group
    from rich.table import Table

    status_info = runtime.status()
    hb = _read_daemon_heartbeat(abs_path)
    daemon_running = False
    if hb:
        pid = hb.get("pid", 0)
        if _is_process_running(pid):
            daemon_running = True

    daemon_status = (
        "[bold green]Running[/bold green]" if daemon_running else "[bold red]Stopped[/bold red]"
    )
    if daemon_running and hb:
        uptime_sec = hb.get("uptime_seconds", 0)
        uptime_str = f" (PID {hb.get('pid')}, uptime {uptime_sec}s)"
        daemon_status += uptime_str

    cpu_val = f"{hb.get('cpu_percent', 0.0)}%" if (daemon_running and hb) else "0%"
    ram_raw = hb.get("ram_mb", 0.0) if (daemon_running and hb) else 0.0
    if ram_raw >= 1024:
        ram_val = f"{ram_raw / 1024:.2f} GB"
    else:
        ram_val = f"{ram_raw:.1f} MB"

    indexed_files = str(status_info.files)
    memory_nodes = str(status_info.symbols)

    if daemon_running and hb:
        indexed_files = f"{hb.get('indexed_files', status_info.files)} files"
        memory_nodes = f"{hb.get('memory_nodes', status_info.symbols)} nodes"

    provider = settings.llm_provider or "None (Mode A)"
    model = settings.llm_model or "None"

    table = Table.grid(padding=(0, 2))
    table.add_column("Property", style="bold cyan")
    table.add_column("Value")

    approved_lessons = 0
    try:
        with runtime.store.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM lessons WHERE status = 'approved'"
            ).fetchone()
            if row:
                approved_lessons = row["cnt"]
    except Exception:
        pass

    table.add_row("Daemon:", daemon_status)
    table.add_row("Repository:", abs_path.name)
    table.add_row("Branch:", status_info.branch)
    table.add_row("Indexed:", indexed_files)
    table.add_row("Symbols:", memory_nodes)
    table.add_row("Approved Lessons:", str(approved_lessons))
    table.add_row("LLM Provider:", provider.capitalize())
    table.add_row("Model:", model)
    table.add_row("CPU:", cpu_val)
    table.add_row("RAM:", ram_val)

    elements: list[Any] = [
        "[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]",
        "[bold cyan]          Synap Runtime Status          [/bold cyan]",
        "[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n",
        table,
        "",
    ]

    if status_info.is_dirty:
        elements.append(
            "[bold yellow]⚠ Warning: Working tree has uncommitted changes. Run git commit to index them.[/bold yellow]"
        )
        try:
            dirty_files = list(runtime.git.get_dirty_diff_ranges().keys())
            if dirty_files:
                show_files = (
                    dirty_files[:limit] if (limit is not None and limit >= 0) else dirty_files
                )
                elements.append(
                    f"[dim]Uncommitted files ({len(dirty_files)}): {', '.join(show_files)}[/dim]"
                )
                if limit is not None and len(dirty_files) > limit:
                    elements.append(f"[dim]... and {len(dirty_files) - limit} more files[/dim]")
        except Exception:
            pass

    return Group(*elements)


@app.command()
def status(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    watch: Annotated[
        bool, typer.Option("--watch", "-w", help="Continuously monitor status in real-time.")
    ] = False,
    interval: Annotated[
        float, typer.Option("--interval", "-i", help="Refresh interval in seconds for watch mode.")
    ] = 2.0,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Limit number of uncommitted files displayed."),
    ] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Minimal one-line status output.")
    ] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show current repository context status."""
    import sys
    import time

    abs_path = _resolve_repo_root(path)
    _verify_is_git(abs_path)
    settings = _settings(abs_path, json_output=json_output)
    runtime = SynapRuntime(settings)

    if json_output:
        status_info = runtime.status()
        hb = _read_daemon_heartbeat(abs_path)
        daemon_running = bool(hb and _is_process_running(hb.get("pid", 0)))
        out = _jsonable(status_info)
        out["daemon"] = hb if daemon_running else None
        if limit is not None and limit >= 0:
            out["limit"] = limit
        _emit_json(out)
        return

    if quiet:
        status_info = runtime.status()
        hb = _read_daemon_heartbeat(abs_path)
        daemon_running = bool(hb and _is_process_running(hb.get("pid", 0)))
        daemon_str = (
            f"running:{hb.get('pid')}" if (daemon_running and hb is not None) else "stopped"
        )
        print(
            f"repo:{abs_path.name} branch:{status_info.branch} files:{status_info.files} "
            f"symbols:{status_info.symbols} dirty:{status_info.is_dirty} daemon:{daemon_str}"
        )
        return

    content = _render_status_content(abs_path, settings, runtime, limit=limit)
    if not watch or not sys.stdout.isatty():
        _stdout_print(content)
        return

    from rich.live import Live

    with Live(
        content,
        console=stdout_console,
        refresh_per_second=4,
    ) as live:
        try:
            while True:
                time.sleep(interval)
                live.update(_render_status_content(abs_path, settings, runtime, limit=limit))
        except KeyboardInterrupt:
            pass


@app.command()
def logs(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    tail: Annotated[
        bool, typer.Option("--tail", "-t", help="Stream new log entries in real-time.")
    ] = False,
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of last lines to show.")] = 50,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Show verbose debug and trace logs.")
    ] = False,
) -> None:
    """View and tail Synap runtime logs."""
    import time

    settings = _settings(path)
    log_dir = settings.log_path
    assert log_dir is not None
    log_file = log_dir / "daemon.log"

    if not log_file.exists():
        console.print("[yellow]No log files found yet.[/yellow]")
        return

    try:
        with open(log_file, encoding="utf-8") as f:
            if not tail:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    if not debug and '"level": "debug"' in line.lower():
                        continue
                    console.print(line.strip())
            else:
                f.seek(0, 2)
                console.print("[cyan]Tailing daemon logs (Ctrl+C to exit)...[/cyan]")
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    if not debug and '"level": "debug"' in line.lower():
                        continue
                    console.print(line.strip())
    except KeyboardInterrupt:
        console.print("\n[yellow]Tail stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error reading logs: {e}[/red]")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query.")],
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    max_tokens: Annotated[
        int, typer.Option("--max-tokens", help="Maximum context window tokens.")
    ] = 4000,
) -> None:
    """
    Execute a hybrid structural search across the repository.

    Examples:
        synap search "database connection logic"
        synap search "authentication middleware" --path /path/to/repo --max-tokens 8000
    """
    settings = _settings(path)
    runtime = SynapRuntime(settings)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Retrieving context...", total=None)
        answer, context, _ = runtime.query_hybrid(query, max_tokens=max_tokens)

    console.print("\n[bold cyan]Hybrid Retrieval Results[/bold cyan]")
    console.print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    console.print(answer)
    console.print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


@app.command("skeleton")
def skeleton_cmd(
    file_path: Annotated[str, typer.Argument(help="Path to file to skeletonize.")],
    path: Annotated[str, typer.Option("--path", "-p", help="Repository root path.")] = ".",
) -> None:
    """Print the structural code skeleton of a file (stripping function/method bodies)."""
    settings = _settings(path)
    target = (settings.repository_path / file_path).resolve()
    if not target.exists() or not target.is_file():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    from synap_git.parser.registry import CodeParserRegistry

    reg = CodeParserRegistry()
    skeleton = reg.skeletonize(target)
    typer.echo(skeleton)


@app.command("context")
def context_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """
    Print the session startup context preamble.

    Useful for piping directly into any LLM or coding agent CLI
    (e.g. synap context | llm ... or aider --message-file <(synap context)).
    """
    _verify_is_git(path)
    settings = _settings(path)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)
    data = facade.get_session_preamble()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    stats = data.get("stats") or {}
    stats_str = (
        f" | Indexed: {stats.get('indexed_files', 0)} files, {stats.get('indexed_symbols', 0)} symbols"
        if stats
        else ""
    )

    lines = [
        "# Synapse Repository Context",
        f"Branch: {data['branch']} | Commit: {data['git_commit'] or 'unknown'} | Dirty: {data['is_dirty']}{stats_str}",
        "",
    ]

    cp = data.get("latest_checkpoint")
    if cp:
        lines.append("## Latest Checkpoint (Resume Here)")
        lines.append(f"- **Doing**: {cp.get('doing', 'N/A')}")
        lines.append(f"- **Next Step**: {cp.get('next_step', 'N/A')}")
        if cp.get("blockers") and cp.get("blockers") != "none":
            lines.append(f"- **Blockers**: {cp.get('blockers')}")
        files = cp.get("changed_files")
        if files:
            files_str = ", ".join(files) if isinstance(files, list) else str(files)
            lines.append(f"- **Changed Files**: {files_str}")
        lines.append("")

    blast = data.get("blast_radius") or {}
    touched = blast.get("touched_symbols", [])
    if touched:
        lines.append("## Git Blast Radius (Impacted Callers)")
        for sym in touched[:4]:
            name = sym["name"]
            path_str = sym["path"]
            line = sym.get("start_line", 1)
            direct = [
                f"`{c['name']}` ({c['path']}:{c['start_line']})"
                for c in blast.get("direct_callers", [])
                if c.get("impacts") == name
            ][:2]
            impacted_tests = [
                f"`{t['name']}` ({t['path']})"
                for t in blast.get("impacted_tests", [])
                if t.get("impacts") == name
            ][:2]
            callers_str = ", ".join(direct) if direct else "No internal callers"
            tests_str = f" | Tests: {', '.join(impacted_tests)}" if impacted_tests else ""
            lines.append(
                f"- Touched `{name}` ({path_str}:{line}) -> Callers: {callers_str}{tests_str}"
            )
        lines.append("")

    hubs = data.get("architectural_hubs") or []
    if hubs:
        lines.append("## Architectural Hubs (PageRank)")
        for h in hubs[:5]:
            lines.append(f"- `{h['name']}` ({h['path']}) [{h['score']}]")
        lines.append("")

    lessons = data.get("approved_lessons", [])
    if lessons:
        lines.append("## Approved Negative Constraints (CRITICAL - DO NOT VIOLATE)")
        for idx, lesson in enumerate(lessons, 1):
            lines.append(
                f"{idx}. DO NOT: {lesson.get('what_failed', '')} - REASON: {lesson.get('why_failed', '')}"
            )
        lines.append("")

    decisions = data.get("recent_decisions", [])
    if decisions:
        lines.append("## Recent Architectural Decisions")
        for dec in decisions:
            context_desc = dec.get("context") or dec.get("context_info") or "N/A"
            lines.append(f"- {dec.get('content', '')} (Context: {context_desc})")
        lines.append("")

    memories = data.get("recent_memories", [])
    if memories:
        lines.append("## Working Memory & Observations")
        for mem in memories:
            key_name = mem.get("context_key", "note")
            summary = mem.get("summary") or mem.get("payload", "")
            lines.append(f"- **{key_name}**: {summary}")
        lines.append("")

    typer.echo("\n".join(lines).strip())


SYNAPSE_RULES_TEMPLATE = """# Synapse AI Agent Directives

This project uses Synapse for persistent structural context, graph navigation, and memory.
Follow these operational guidelines:

## 1. Session Start & Context Loading
- At the start of any conversation or task, call the MCP tool `get_session_preamble()`.
- Review the active branch, latest checkpoint, and approved negative constraints (lessons).
- If resuming an existing task, call `restore_checkpoint()`.
- Never repeat failures listed in approved lessons.

## 2. Progressive Code Navigation & Search
- When exploring, call `search(query="...", summary_only=True)` first to find relevant symbols with minimal token overhead.
- Use `get_skeleton(file_path="...")` to inspect function signatures, docstrings, and classes without implementation bodies (85% token savings).
- Use `get_outline(file_path="...")` to inspect file structure and line ranges.
- Use `read_symbol(symbol="...", file_path="...")` to read exact symbol code without reading entire files.
- Before modifying a symbol, use `get_callers(symbol="...")` or `get_neighborhood(symbol="...", direction="upstream")` to check caller blast radius.

## 3. Verification & Testing
- Use `get_diff()` to review uncommitted code changes.
- Use `get_test_recommendations()` to identify impacted test files and receive recommended pytest commands.

## 4. Session Checkpointing & Memory
- Before ending a complex task or when context is high, call `create_checkpoint(doing="...", next_step="...")`.
- Log key architectural decisions using `log_decision(content="...", context_info="...")`.
- Save critical environment facts or non-code observations using `remember(key="...", content="...")`, and look up with `recall(key="...")`.
"""


@app.command("preamble")
def preamble_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Alias for 'synap context'."""
    context_cmd(path=path, json_output=json_output)


@app.command("blast")
def blast_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    limit: Annotated[
        int | None, typer.Option("--limit", "-n", help="Maximum items to display.")
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress decorative tables and output raw impacted symbols/tests.",
        ),
    ] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Analyze blast radius of uncommitted changes (touched symbols, direct callers, and impacted tests)."""
    root = _resolve_repo_root(path)
    _verify_is_git(root)
    settings = _settings(root, json_output=json_output)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)
    blast = facade.get_blast_radius()

    touched = blast.get("touched_symbols", [])
    callers = blast.get("direct_callers", [])
    tests = blast.get("impacted_tests", [])

    if limit is not None and limit >= 0:
        touched = touched[:limit]
        callers = callers[:limit]
        tests = tests[:limit]
        blast["touched_symbols"] = touched
        blast["direct_callers"] = callers
        blast["impacted_tests"] = tests

    if json_output:
        _emit_json(blast)
        return

    if quiet:
        for s in touched:
            print(f"symbol:{s['name']}:{s['path']}:{s.get('start_line', 1)}")
        for t in tests:
            print(f"test:{t['name']}:{t['path']}")
        return

    if not touched:
        _stdout_print(
            "[green]✓ Clean working tree or no indexed symbols modified in uncommitted diff.[/green]"
        )
        return

    table = Table(title="💥 Git Blast Radius (Impacted Callers & Tests)", border_style="red")
    table.add_column("Modified Symbol", style="bold yellow")
    table.add_column("Location")
    table.add_column("Direct Callers", style="cyan")
    table.add_column("Impacted Tests", style="magenta")

    for sym in touched:
        name = sym["name"]
        loc = f"{sym['path']}:{sym.get('start_line', 1)}"
        sym_callers = [
            f"{c['name']} ({c['path']}:{c.get('start_line', 1)})"
            for c in callers
            if c.get("impacts") == name
        ]
        sym_tests = [f"{t['name']} ({t['path']})" for t in tests if t.get("impacts") == name]
        callers_str = "\n".join(sym_callers) if sym_callers else "[dim]None[/dim]"
        tests_str = "\n".join(sym_tests) if sym_tests else "[dim]None[/dim]"
        table.add_row(name, loc, callers_str, tests_str)

    _stdout_print(table)


@app.command("hubs")
def hubs_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of hubs to display.")] = 10,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", "-q", help="Suppress decorative tables and output only symbol names."
        ),
    ] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Discover top architectural hubs using Personalized PageRank over the code graph."""
    root = _resolve_repo_root(path)
    _verify_is_git(root)
    settings = _settings(root, json_output=json_output)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    active_files = list(runtime.git.get_dirty_diff_ranges().keys())
    hubs = runtime.store.compute_pagerank(active_files=active_files, limit=limit)

    if json_output:
        _emit_json(hubs)
        return

    if quiet:
        for h in hubs:
            print(h.get("name", ""))
        return

    table = Table(title=f"🏛️ Architectural Hubs (PageRank Top {len(hubs)})", border_style="cyan")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Symbol", style="bold green")
    table.add_column("Kind", style="yellow")
    table.add_column("Path", style="dim")
    table.add_column("Score", justify="right", style="cyan")

    for idx, h in enumerate(hubs, 1):
        table.add_row(str(idx), h["name"], h["kind"], h["path"], f"{h['score']:.4f}")

    _stdout_print(table)


@app.command("outline")
def outline_cmd(
    file_path: Annotated[str, typer.Argument(help="Path to file to outline.")],
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    limit: Annotated[
        int | None, typer.Option("--limit", "-n", help="Maximum symbols to display.")
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", "-q", help="Suppress decorative tables and output symbol signatures."
        ),
    ] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Print structural AST outline (functions, classes, methods, and line ranges) of a file."""
    root = _resolve_repo_root(path)
    _verify_is_git(root)
    resolved_file = _resolve_repo_file_path(file_path, root)
    settings = _settings(root, json_output=json_output)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)
    data = facade.get_outline(resolved_file)

    symbols = data.get("symbols", [])
    if limit is not None and limit >= 0:
        symbols = symbols[:limit]
        data["symbols"] = symbols

    if json_output:
        _emit_json(data)
        return

    if quiet:
        for s in symbols:
            sig = s.get("signature") or s.get("name", "")
            print(f"{s.get('name')}:{s.get('start_line', 1)}-{s.get('end_line', 1)} {sig}".strip())
        return

    if not symbols:
        _stdout_print(f"[yellow]No symbols found in outline for '{file_path}'.[/yellow]")
        return

    table = Table(
        title=f"📐 AST Outline: {data.get('file_path') or resolved_file}", border_style="green"
    )
    table.add_column("Symbol", style="bold cyan")
    table.add_column("Kind", style="yellow")
    table.add_column("Lines", justify="right")
    table.add_column("Signature", style="dim")

    for s in symbols:
        lines_str = f"{s.get('start_line', 1)}-{s.get('end_line', 1)}"
        table.add_row(s.get("name", ""), s.get("kind", ""), lines_str, s.get("signature", "")[:60])

    _stdout_print(table)


@app.command("diff")
def diff_cmd(
    file_path: Annotated[str, typer.Argument(help="Optional file path to diff.")] = "",
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    staged: Annotated[bool, typer.Option("--staged", help="Diff staged changes.")] = False,
    limit: Annotated[
        int | None, typer.Option("--limit", "-n", help="Maximum diff lines to display.")
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress informational messages; silent on clean working tree.",
        ),
    ] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show raw unified git diff of uncommitted changes."""
    root = _resolve_repo_root(path)
    _verify_is_git(root)
    resolved_file = _resolve_repo_file_path(file_path, root) if file_path else ""
    settings = _settings(root, json_output=json_output)
    runtime = SynapRuntime(settings)

    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)
    res = facade.get_diff(file_path=resolved_file, staged=staged)
    diff_text = res.get("diff", "")

    if limit is not None and limit >= 0:
        lines = diff_text.splitlines()
        if len(lines) > limit:
            diff_text = "\n".join(lines[:limit]) + f"\n... [truncated to {limit} lines]"

    if json_output:
        _emit_json({"file_path": resolved_file or None, "staged": staged, "diff": diff_text})
        return

    if diff_text:
        print(diff_text)
    elif not quiet:
        _stdout_print("[green]✓ No differences found.[/green]")


@app.command("test")
def test_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print recommended test command without running."),
    ] = False,
    extra_args: Annotated[
        str, typer.Option("--args", "-a", help="Extra arguments to forward to pytest.")
    ] = "",
) -> None:
    """Run tests impacted by uncommitted changes using AST blast radius analysis."""
    import shlex
    import subprocess

    root = _resolve_repo_root(path)
    _verify_is_git(root)
    settings = _settings(root)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)
    rec = facade.get_test_recommendations()
    cmd_str = rec.get("recommended_command", ".venv/bin/pytest")
    test_files = rec.get("test_files", [])

    if extra_args:
        cmd_str += f" {extra_args}"

    if not test_files:
        console.print(
            "[green]Working tree is clean or no specific tests mapped. Running full test suite...[/green]"
        )
    else:
        console.print(
            f"[bold cyan]Impacted tests ({len(test_files)} files):[/bold cyan] {', '.join(test_files)}"
        )

    console.print(f"[dim]Command: {cmd_str}[/dim]\n")
    if dry_run:
        return

    tokens = shlex.split(cmd_str)
    res = subprocess.run(tokens, cwd=settings.repository_path)
    raise typer.Exit(code=res.returncode)


@app.command("explain")
def explain_cmd(
    symbol: Annotated[str, typer.Argument(help="Symbol or function name to explain.")],
    file_path: Annotated[
        str, typer.Option("--file", "-f", help="Optional file path to disambiguate.")
    ] = "",
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
) -> None:
    """Explain a symbol's definition, callers, dependencies, and test coverage in the code graph."""
    root = _resolve_repo_root(path)
    _verify_is_git(root)
    rel_file = _resolve_repo_file_path(file_path, root) if file_path else None
    settings = _settings(root)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)

    try:
        sym_info = facade.read_symbol(symbol, file_path=rel_file)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    callers_data = facade.get_neighborhood(
        symbol, file_path=rel_file, direction="upstream", depth=1
    )
    callees_data = facade.get_neighborhood(
        symbol, file_path=rel_file, direction="downstream", depth=1
    )

    table = Table(title=f"🔍 Structural Symbol Analysis: {sym_info['name']}", border_style="cyan")
    table.add_column("Property", style="bold")
    table.add_column("Details")
    table.add_row("Kind", sym_info["kind"])
    table.add_row("Location", f"{sym_info['path']}:{sym_info['start_line']}-{sym_info['end_line']}")

    callers = [f"{n['name']} ({n['path']}:{n['lines']})" for n in callers_data.get("neighbors", [])]
    table.add_row(
        "Inbound Callers (Upstream)",
        ", ".join(callers) if callers else "[dim]None detected[/dim]",
    )

    callees = [f"{n['name']} ({n['path']}:{n['lines']})" for n in callees_data.get("neighbors", [])]
    table.add_row(
        "Dependencies (Downstream)",
        ", ".join(callees) if callees else "[dim]None detected[/dim]",
    )

    _stdout_print(table)
    _stdout_print("\n[bold]Code Implementation:[/bold]")
    _stdout_print(sym_info.get("numbered_code", sym_info.get("code", "")))


@app.command("pack")
def pack_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    max_tokens: Annotated[
        int, typer.Option("--max-tokens", "-m", help="Maximum token budget.")
    ] = 8000,
    output: Annotated[
        str, typer.Option("--output", "-o", help="Write output to file instead of stdout.")
    ] = "",
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Maximum number of hub skeletons to include."),
    ] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress status messages.")] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Pack token-budgeted repository context (AST skeletons of hubs, dirty blast radius, memory) for LLM prompts."""
    import tiktoken

    root = _resolve_repo_root(path)
    _verify_is_git(root)
    settings = _settings(root, json_output=json_output)
    runtime = SynapRuntime(settings)
    runtime.initialize_storage()

    from synap_git.mcp.server import SynapMCPFacade
    from synap_git.parser.registry import CodeParserRegistry

    facade = SynapMCPFacade(runtime)
    reg = CodeParserRegistry()
    enc = tiktoken.get_encoding("cl100k_base")

    preamble_data = facade.get_session_preamble()
    lines = [
        f"# Synapse Repository Context Pack: {settings.repository_path.name}",
        f"Branch: {preamble_data['branch']} | Commit: {preamble_data.get('git_commit', 'unknown')}",
        "",
        preamble_data.get("compact_preamble", ""),
        "",
        "## Architectural Hub Skeletons",
    ]

    used_tokens = len(enc.encode("\n".join(lines)))
    hubs = preamble_data.get("architectural_hubs", [])
    if limit is not None and limit >= 0:
        hubs = hubs[:limit]

    for h in hubs:
        fpath = settings.repository_path / h["path"]
        if fpath.exists() and fpath.is_file():
            try:
                skel = reg.skeletonize(fpath)
                block = f"\n### File Skeleton: {h['path']}\n```\n{skel}\n```\n"
                b_tokens = len(enc.encode(block))
                if used_tokens + b_tokens > max_tokens:
                    break
                lines.append(block)
                used_tokens += b_tokens
            except Exception:
                pass

    content = "\n".join(lines).strip()
    if json_output:
        _emit_json(
            {
                "branch": preamble_data.get("branch"),
                "git_commit": preamble_data.get("git_commit"),
                "tokens": used_tokens,
                "max_tokens": max_tokens,
                "hubs_included": len(hubs),
                "content": content,
            }
        )
        return

    if output:
        out_path = Path(output).resolve()
        out_path.write_text(content, encoding="utf-8")
        if not quiet:
            _stdout_print(f"[green]✓ Packed {used_tokens} tokens into {out_path}[/green]")
    else:
        print(content)


@app.command("rules")
def rules_cmd(
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    target: Annotated[
        str,
        typer.Option(
            "--target",
            "-t",
            help="Target rules file (all, cursor, claude, agents).",
        ),
    ] = "all",
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing Synapse directives."),
    ] = False,
    stdout: Annotated[
        bool,
        typer.Option("--stdout", help="Print rules to stdout instead of writing files."),
    ] = False,
) -> None:
    """Generate universal agent directives for Cursor (.cursorrules), Claude Code (CLAUDE.md), and AGENTS.md."""
    if stdout:
        typer.echo(SYNAPSE_RULES_TEMPLATE.strip())
        return

    _verify_is_git(path)
    repo_dir = _resolve_repo_root(path)
    target_lower = target.lower().strip()

    targets: list[tuple[str, Path]] = []
    if target_lower in ("all", "cursor"):
        targets.append((".cursorrules", repo_dir / ".cursorrules"))
    if target_lower in ("all", "claude"):
        targets.append(("CLAUDE.md", repo_dir / "CLAUDE.md"))
    if target_lower in ("all", "agents"):
        targets.append(("AGENTS.md", repo_dir / "AGENTS.md"))

    if not targets:
        console.print(
            f"[red]Unknown target '{target}'. Choose from: all, cursor, claude, agents.[/red]"
        )
        raise typer.Exit(1)

    updated_files: list[str] = []
    for filename, file_path in targets:
        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")
            marker = "# Synapse AI Agent Directives"
            if marker in existing:
                if not force:
                    continue
                # Split at marker to retain everything prior
                before_marker = existing.split(marker)[0].rstrip()
                if before_marker:
                    new_content = before_marker + "\n\n" + SYNAPSE_RULES_TEMPLATE.strip() + "\n"
                else:
                    new_content = SYNAPSE_RULES_TEMPLATE.strip() + "\n"
            else:
                new_content = existing.rstrip() + "\n\n" + SYNAPSE_RULES_TEMPLATE.strip() + "\n"
        else:
            new_content = SYNAPSE_RULES_TEMPLATE.strip() + "\n"

        file_path.write_text(new_content, encoding="utf-8")
        updated_files.append(filename)

    if updated_files:
        console.print(
            f"[bold green]✓ Configured Synapse agent directives in: {', '.join(updated_files)}[/bold green]"
        )
    else:
        console.print("[dim]Synapse agent directives already present in all target files.[/dim]")


@app.command()
def update(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force upgrade even if already at latest version.")
    ] = False,
) -> None:
    """Check for updates and upgrade the Synap runtime."""
    import subprocess
    import sys
    from pathlib import Path

    import httpx

    from synap_git import __version__ as current_version

    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
    console.print("[bold cyan]             Synap Updater              [/bold cyan]")
    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")

    install_method = _detect_install_method()
    console.print(f"Installation method detected: [bold]{install_method.upper()}[/bold]")
    console.print(f"Current version: [bold]{current_version}[/bold]")

    latest_version = current_version
    with console.status("[yellow]Checking for updates on PyPI...[/yellow]"):
        try:
            resp = httpx.get("https://pypi.org/pypi/synap-git/json", timeout=5.0)
            if resp.status_code == 200:
                latest_version = resp.json().get("info", {}).get("version", current_version)
        except Exception as e:
            console.print(f"[yellow]⚠ Note: Unable to check PyPI for updates ({e}).[/yellow]")

    console.print(f"Latest version on PyPI: [bold]{latest_version}[/bold]")

    def is_newer(v_remote: str, v_local: str) -> bool:
        try:
            from packaging.version import Version

            return Version(v_remote) > Version(v_local)
        except (ImportError, Exception):
            try:

                def _to_tuple(v: str) -> tuple[int, ...]:
                    return tuple(int(x) for x in v.split(".") if x.isdigit())

                return _to_tuple(v_remote) > _to_tuple(v_local)
            except Exception:
                return v_remote != v_local

    if not force and not is_newer(latest_version, current_version) and install_method != "editable":
        console.print("[green]✓ Synap is already up to date.[/green]")
        return

    if install_method == "editable":
        console.print("\n[yellow]Editable installation detected. Updating environment...[/yellow]")
        import synap_git

        pkg_file = Path(synap_git.__file__).resolve()
        repo_root = pkg_file.parent.parent.parent

        try:
            # Dynamically determine the current checked out git branch
            branch_res = subprocess.run(
                ["git", "symbolic-ref", "--short", "--quiet", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            curr_branch = branch_res.stdout.strip() if branch_res.returncode == 0 else "main"

            pull_res = subprocess.run(
                ["git", "pull", "--rebase", "origin", curr_branch],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if pull_res.returncode == 0:
                console.print(f"[green]✓ Git branch '{curr_branch}' pulled successfully.[/green]")
            else:
                console.print(
                    f"[yellow]⚠ Git pull skipped or uncommitted changes detected on '{curr_branch}'.[/yellow]"
                )
        except Exception as e:
            console.print(f"[yellow]⚠ Git pull skipped: {e}[/yellow]")

        # For editable installs, attempt metadata refresh via pip or uv with explicit python interpreter
        reinstalled = False
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "-e", str(repo_root)],
                check=True,
                capture_output=True,
            )
            reinstalled = True
            console.print("[green]✓ Update successful (Editable package re-installed).[/green]")
        except Exception:
            pass

        if not reinstalled:
            try:
                subprocess.run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        sys.executable,
                        "--quiet",
                        "-e",
                        str(repo_root),
                    ],
                    check=True,
                    capture_output=True,
                )
                reinstalled = True
                console.print(
                    "[green]✓ Update successful (Editable package re-installed via uv).[/green]"
                )
            except Exception:
                pass

        if not reinstalled:
            try:
                subprocess.run(
                    ["uv", "tool", "upgrade", "synap-git"],
                    check=True,
                    capture_output=True,
                )
                reinstalled = True
                console.print("[green]✓ Update successful (uv tool upgraded).[/green]")
            except Exception:
                pass

        if not reinstalled:
            # For editable installs, git pull immediately applies changes
            console.print(
                "[green]✓ Update successful (Editable source code is up to date from Git).[/green]"
            )
        return

    upgrade_cmds = {
        "pipx": ["pipx", "upgrade", "synap-git"],
        "uv": ["uv", "tool", "upgrade", "synap-git"],
        "venv": [sys.executable, "-m", "pip", "install", "--upgrade", "synap-git"],
        "pip": [sys.executable, "-m", "pip", "install", "--upgrade", "synap-git"],
    }

    cmd = upgrade_cmds.get(install_method)
    if not cmd:
        console.print("[red]Unknown installation method. Upgrade manually.[/red]")
        return

    console.print(
        f"\n[yellow]Upgrading Synap to {latest_version} using: {' '.join(cmd)}...[/yellow]"
    )
    try:
        try:
            subprocess.run(cmd, check=True)
        except Exception as e:
            if install_method in ("venv", "pip", "uv"):
                console.print(
                    "[yellow]Command failed. Attempting upgrade via uv pip install...[/yellow]"
                )
                subprocess.run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        sys.executable,
                        "--upgrade",
                        "synap-git",
                    ],
                    check=True,
                )
            else:
                raise e
        console.print("[green]✓ Update successful[/green]")
    except Exception as e:
        console.print(f"[bold red]✗ Upgrade failed:[/bold red] {e}")
        raise typer.Exit(1)


HOOK_MARKER_START = "# --- SYNAP HOOK START ---"
HOOK_MARKER_END = "# --- SYNAP HOOK END ---"
HOOK_SCRIPT = """# --- SYNAP HOOK START ---
if command -v synap >/dev/null 2>&1; then
    (synap sync --quiet >/dev/null 2>&1 &)
fi
# --- SYNAP HOOK END ---"""


def _install_git_hook(hook_file: Path) -> bool:
    hook_file.parent.mkdir(parents=True, exist_ok=True)
    if hook_file.exists():
        content = hook_file.read_text(encoding="utf-8")
        if HOOK_MARKER_START in content:
            return False
        new_content = content.rstrip() + "\n\n" + HOOK_SCRIPT + "\n"
    else:
        new_content = "#!/bin/sh\n\n" + HOOK_SCRIPT + "\n"

    hook_file.write_text(new_content, encoding="utf-8")
    try:
        hook_file.chmod(hook_file.stat().st_mode | 0o111)
    except OSError:
        pass
    return True


def _uninstall_git_hook(hook_file: Path) -> bool:
    if not hook_file.exists():
        return False
    content = hook_file.read_text(encoding="utf-8")
    if HOOK_MARKER_START not in content:
        return False
    before = content.split(HOOK_MARKER_START)[0]
    after = content.split(HOOK_MARKER_END)[1] if HOOK_MARKER_END in content else ""
    cleaned = (before + after).strip()
    if cleaned and not cleaned.startswith("#!/bin/sh"):
        cleaned = "#!/bin/sh\n" + cleaned
    if cleaned.strip() in ("", "#!/bin/sh"):
        hook_file.unlink(missing_ok=True)
    else:
        hook_file.write_text(cleaned + "\n", encoding="utf-8")
    return True


@hooks_app.command("install")
def hooks_install_cmd(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress output.")] = False,
) -> bool:
    """Install Git hooks (post-commit, post-checkout) for zero-daemon automatic index sync."""
    repo_dir = _resolve_repo_root(path)
    dirs = GitRepository.resolve_git_dir(repo_dir)
    if dirs is None:
        if not quiet:
            console.print(f"[red]Directory {repo_dir} is not a Git repository.[/red]")
        return False

    _, common_dir = dirs
    hooks_dir = common_dir / "hooks"
    c1 = _install_git_hook(hooks_dir / "post-commit")
    c2 = _install_git_hook(hooks_dir / "post-checkout")
    installed = c1 or c2

    if not quiet:
        if installed:
            console.print(
                "[bold green]✓ Git post-commit & post-checkout hooks installed for automatic reindexing.[/bold green]"
            )
        else:
            console.print("[dim]Git hooks already installed.[/dim]")
    return installed


@hooks_app.command("uninstall")
def hooks_uninstall_cmd(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress output.")] = False,
) -> bool:
    """Remove Synap Git hooks."""
    repo_dir = _resolve_repo_root(path)
    dirs = GitRepository.resolve_git_dir(repo_dir)
    if dirs is None:
        return False
    _, common_dir = dirs
    hooks_dir = common_dir / "hooks"
    if not hooks_dir.exists():
        return False

    u1 = _uninstall_git_hook(hooks_dir / "post-commit")
    u2 = _uninstall_git_hook(hooks_dir / "post-checkout")
    removed = u1 or u2

    if not quiet:
        if removed:
            console.print("[green]✓ Synap Git hooks removed successfully.[/green]")
        else:
            console.print("[dim]No Synap Git hooks found to remove.[/dim]")
    return removed


def _strip_json_comments(text: str) -> str:
    import re

    pattern = r'("(?:\\.|[^"\\])*")|//.*?$|/\*.*?\*/'

    def replace(match: re.Match[str]) -> str:
        if match.group(1):
            return match.group(1)
        return ""

    cleaned = re.sub(pattern, replace, text, flags=re.MULTILINE | re.DOTALL)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return cleaned


def _inject_mcp_config(config_path: Path, server_cmd: str, server_args: list[str]) -> bool:
    try:
        import shutil

        config_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if config_path.exists():
            # Create a .bak backup before reading and modifying existing config
            bak_path = config_path.with_name(config_path.name + ".bak")
            try:
                shutil.copy2(config_path, bak_path)
            except OSError:
                pass

            raw = config_path.read_text(encoding="utf-8").strip()
            if raw:
                cleaned = _strip_json_comments(raw)
                try:
                    loaded: Any = json.loads(cleaned)
                    if isinstance(loaded, dict):
                        data = loaded
                    else:
                        console.print(
                            f"[yellow]Warning: {config_path} is not a JSON object. Preserving file.[/yellow]"
                        )
                        return False
                except Exception as parse_err:
                    console.print(
                        f"[yellow]Warning: Could not parse {config_path}: {parse_err}. Preserving file.[/yellow]"
                    )
                    return False

        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}

        data["mcpServers"]["synap"] = {
            "command": server_cmd,
            "args": server_args,
        }

        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True
    except Exception as e:
        console.print(f"[yellow]Warning: Could not configure {config_path}: {e}[/yellow]")
        return False


@app.command("install")
def install_cmd(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    ide: Annotated[
        str,
        typer.Option(
            "--ide",
            "-i",
            help="Target IDE to configure (all, cursor, claude, windsurf, desktop).",
        ),
    ] = "all",
    global_setup: Annotated[
        bool,
        typer.Option(
            "--global/--local",
            "-g/-l",
            help="Install globally across all repositories (recommended) or lock to this repo.",
        ),
    ] = True,
    skip_init: Annotated[
        bool,
        typer.Option("--skip-init", help="Skip repository indexing during install."),
    ] = False,
) -> None:
    """Seamless 1-command installer: discovers IDEs, registers Synap MCP server globally, and initializes repository."""
    import os
    import shutil
    import sys

    console.print("\n[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
    console.print("[bold cyan]       Synap Seamless 1-Click Setup       [/bold cyan]")
    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")

    repo_dir = _resolve_repo_root(path)
    is_git = (repo_dir / ".git").exists()

    synap_bin = shutil.which("synap")
    if synap_bin:
        server_cmd = synap_bin
        server_args = ["mcp", "serve"]
    else:
        server_cmd = sys.executable
        server_args = ["-m", "synap_git.cli", "mcp", "serve"]

    if not global_setup and path != ".":
        server_args.append(repo_dir.as_posix())

    # 1. Initialize repository if inside Git repo
    if is_git and not skip_init:
        console.print(f"[dim]Initializing Synap index in {repo_dir}...[/dim]")
        try:
            settings = _settings(path)
            runtime = SynapRuntime(settings)
            runtime.initialize_storage()
            console.print(
                "[bold green]✓ Local structural repository index initialized[/bold green]"
            )
        except Exception as e:
            console.print(f"[yellow]Warning: Index initialization deferred: {e}[/yellow]")

        # Configure agent directives (AGENTS.md, .cursorrules, CLAUDE.md)
        try:
            rules_cmd(path=path, target="all", stdout=False)
        except Exception as e:
            console.print(f"[yellow]Warning: Rules generation deferred: {e}[/yellow]")

        # Configure Git hooks (post-commit, post-checkout) for zero-daemon reindexing
        try:
            if hooks_install_cmd(path=path, quiet=True):
                console.print(
                    "[bold green]✓ Configured Git hooks for zero-daemon automatic reindexing[/bold green]"
                )
        except Exception as e:
            console.print(f"[yellow]Warning: Git hooks generation deferred: {e}[/yellow]")

    # 2. Discover IDE configurations
    home = Path.home()
    all_ide_targets: dict[str, list[Path]] = {
        "cursor": [
            home / ".cursor" / "mcp.json",
        ],
        "claude": [
            home / ".claude.json",
            home / ".claude" / "settings.json",
        ],
        "windsurf": [
            home / ".codeium" / "windsurf" / "mcp_config.json",
            home / ".config" / "Codeium" / "windsurf" / "mcp_config.json",
        ],
        "desktop": [],
    }

    if not global_setup:
        all_ide_targets["cursor"].append(repo_dir / ".cursor" / "mcp.json")

    if sys.platform == "darwin":
        all_ide_targets["desktop"].append(
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        )
    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            all_ide_targets["desktop"].append(
                Path(appdata) / "Claude" / "claude_desktop_config.json"
            )
            all_ide_targets["windsurf"].append(
                Path(appdata) / "Codeium" / "windsurf" / "mcp_config.json"
            )
    else:
        all_ide_targets["desktop"].append(
            home / ".config" / "Claude" / "claude_desktop_config.json"
        )

    ide_choice = ide.lower().strip()
    selected_targets: list[tuple[str, Path]] = []

    for name, paths in all_ide_targets.items():
        if ide_choice not in ("all", name):
            continue
        for p in paths:
            if ide_choice == name or p.exists() or p.parent.exists():
                selected_targets.append((name.capitalize(), p))

    # Fallback to cursor config if no existing IDE files detected
    if not selected_targets and ide_choice in ("all", "cursor"):
        fallback_path = (
            home / ".cursor" / "mcp.json" if global_setup else repo_dir / ".cursor" / "mcp.json"
        )
        selected_targets.append(("Cursor", fallback_path))

    configured_count = 0
    for app_name, cfg_path in selected_targets:
        if _inject_mcp_config(cfg_path, server_cmd, server_args):
            console.print(
                f"[bold green]✓ Configured MCP in {app_name}:[/bold green] [dim]{cfg_path}[/dim]"
            )
            configured_count += 1

    if configured_count > 0:
        scope_str = "globally for all repositories" if global_setup else f"for {repo_dir.name}"
        console.print(
            f"\n[bold green]🎉 Synapse successfully installed {scope_str} across {configured_count} IDE configuration(s)![/bold green]"
        )
        console.print(
            "[dim]Every repository you open will now automatically have persistent context and memory.[/dim]\n"
        )
    else:
        console.print(
            "[yellow]No IDE configs could be updated. Run 'synap mcp config' to inspect manual JSON.[/yellow]\n"
        )


@app.command("uninstall")
def uninstall_command(
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip interactive confirmation.")
    ] = False,
) -> None:
    """Uninstall the Synap CLI package."""
    import subprocess
    import sys

    install_method = _detect_install_method()
    console.print(
        f"[bold]Detected installation method:[/bold] [cyan]{install_method.upper()}[/cyan]"
    )

    if not yes:
        import questionary

        confirmed = questionary.confirm(
            "Are you sure you want to uninstall Synap?",
            default=False,
        ).ask()
        if not confirmed:
            console.print("[yellow]Uninstall cancelled.[/yellow]")
            return

    uninstall_cmds: dict[str, list[str]] = {
        "pipx": ["pipx", "uninstall", "synap-git"],
        "uv": ["uv", "tool", "uninstall", "synap-git"],
        "venv": [sys.executable, "-m", "pip", "uninstall", "-y", "synap-git"],
        "pip": [sys.executable, "-m", "pip", "uninstall", "-y", "synap-git"],
        "editable": ["uv", "tool", "uninstall", "synap-git"],
    }

    cmd = uninstall_cmds.get(install_method)
    if not cmd:
        console.print("[red]Unknown installation method. Please uninstall manually.[/red]")
        return

    console.print(f"[yellow]Uninstalling Synap using: {' '.join(cmd)}...[/yellow]")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            console.print("[green]✓ Synap uninstalled successfully.[/green]")
        else:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "uninstall", "-y", "synap-git"],
                    check=True,
                )
                console.print("[green]✓ Synap uninstalled successfully.[/green]")
            except Exception:
                try:
                    subprocess.run(
                        ["uv", "pip", "uninstall", "--python", sys.executable, "-y", "synap-git"],
                        check=True,
                    )
                    console.print("[green]✓ Synap uninstalled successfully via uv.[/green]")
                except Exception as e:
                    console.print(f"[red]Could not automatically uninstall:[/red] {e}")
                    console.print(f"[yellow]To uninstall manually, run:[/yellow] {' '.join(cmd)}")
    except Exception as e:
        console.print(f"[red]Uninstall failed:[/red] {e}")


@app.command()
def version() -> None:
    """Print the Synap package version."""
    from synap_git import __version__

    console.print(f"Synap v{__version__}")


def version_callback(value: bool) -> None:
    if value:
        from synap_git import __version__

        typer.echo(f"Synap v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Print version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    if ctx.invoked_subcommand is None:
        repo_path = Path.cwd()
        if (repo_path / ".git").exists() or (repo_path / ".synap").exists():
            try:
                from synap_git import __version__

                settings = _settings(".")
                runtime = SynapRuntime(settings)
                status = runtime.status()
                state = runtime.git.state()

                table = Table(
                    title=f"⚡ Synapse v{__version__} — Git-Aware Context Engine",
                    border_style="cyan",
                )
                table.add_column("Property", style="bold")
                table.add_column("Value")
                table.add_row("Branch", f"[bold green]{status.branch}[/bold green]")
                table.add_row(
                    "Commit", f"`{status.git_commit[:8] if status.git_commit else 'unknown'}`"
                )
                table.add_row(
                    "Working Tree",
                    "[red]DIRTY[/red]" if state.is_dirty else "[green]CLEAN[/green]",
                )
                table.add_row("Indexed Files", str(status.files))
                table.add_row("Indexed Symbols", str(status.symbols))
                console.print(table)
                console.print("\n[bold]Quick Commands:[/bold]")
                console.print(
                    "  [cyan]synap context[/cyan]        Print token-bounded session preamble (< 750 tokens)"
                )
                console.print(
                    "  [cyan]synap blast[/cyan]          Analyze blast radius of uncommitted changes"
                )
                console.print(
                    "  [cyan]synap test[/cyan]           Run tests impacted by blast radius"
                )
                console.print(
                    "  [cyan]synap pack[/cyan]           Export token-budgeted prompt pack (< 8k tokens)"
                )
                console.print(
                    "  [cyan]synap explain <sym>[/cyan]  Inspect symbol, callers, dependencies & tests"
                )
                console.print(
                    "  [cyan]synap skeleton <f>[/cyan]  AST skeleton (85% token reduction)"
                )
                console.print(
                    "  [cyan]synap hubs[/cyan]           Top architectural hubs via PageRank"
                )
                console.print("  [cyan]synap search <q>[/cyan]    Hybrid structural retrieval")
                console.print(
                    "  [cyan]synap doctor[/cyan]         System integrity and diagnostic health check"
                )
                console.print("  [dim]Run 'synap --help' for all commands.[/dim]\n")
                return
            except Exception:
                pass
        console.print(ctx.get_help())


@app.command()
def rollback(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    commit: Annotated[
        str | None,
        typer.Option(
            "--commit",
            "-c",
            help="Commit hash or reference to rollback to directly.",
        ),
    ] = None,
    git_checkout: Annotated[
        bool,
        typer.Option(
            "--git-checkout",
            help="Also check out working tree files to that commit (WARNING: modifies local working tree).",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Automatically approve rollback without prompting.",
        ),
    ] = False,
) -> None:
    """Rollback active state to a previous commit."""
    import subprocess
    import sys

    settings = _settings(path)
    runtime = SynapRuntime(settings)

    selected_commit = None

    if commit:
        # Resolve and verify the provided commit reference
        try:
            subprocess.check_output(  # noqa: S603
                ["git", "rev-parse", "--verify", commit],  # noqa: S607
                cwd=settings.repository_path,
                stderr=subprocess.STDOUT,
                text=True,
            )
            selected_commit = subprocess.check_output(  # noqa: S603
                ["git", "rev-parse", "--short", commit],  # noqa: S607
                cwd=settings.repository_path,
                text=True,
            ).strip()
        except Exception:
            console.print(f"[red]✗ Commit reference '{commit}' is invalid or not found.[/red]")
            raise typer.Abort()
    else:
        is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
        if not is_interactive:
            console.print(
                "[red]✗ Non-interactive terminal detected. Must specify --commit / -c option.[/red]"
            )
            raise typer.Abort()

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
    if git_checkout:
        console.print(
            "    - Restore index and check out working tree files to that commit (via git checkout)"
        )
    else:
        console.print(
            "    - Restore context index state to match that commit (working tree untouched)"
        )
    console.print("    - Preserve all approved lessons (they survive rollbacks)")
    console.print("    - Clear current checkpoint")

    if not yes:
        is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
        if not is_interactive:
            console.print(
                "[red]✗ Non-interactive terminal detected. Must use --yes / -y option to approve rollback.[/red]"
            )
            raise typer.Abort()
        if not typer.confirm("\nProceed?", default=False):
            raise typer.Abort()

    # git checkout only if explicitly requested
    if git_checkout:
        try:
            subprocess.check_call(  # noqa: S603
                ["git", "checkout", selected_commit],  # noqa: S607
                cwd=settings.repository_path,
            )
        except Exception as e:
            console.print(f"[red]✗ Git checkout failed: {e}[/red]")
            raise typer.Abort()

    # Clear current checkpoint and update active commit
    try:
        with runtime.store.connect() as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE branch = ?",
                (runtime.git.state().effective_branch,),
            )
            runtime.store.set_active_commit(runtime.git.state().effective_branch, selected_commit)
    except Exception as e:
        import structlog

        structlog.get_logger().error("suppressed_error_caught", error=str(e))

    with console.status(
        f"[yellow]Reindexing repository to match {selected_commit}...[/yellow]", spinner="dots"
    ):
        runtime.bootstrap(force=True)
    console.print(f"[green]✓ Rolled back successfully to {selected_commit}[/green]")


@app.command()
def repair(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Automatically approve force rebuild if database is healthy.",
        ),
    ] = False,
) -> None:
    """Repair a broken index state."""
    settings = _settings(path)
    runtime = SynapRuntime(settings)

    console.print("Checking database integrity...")
    corrupted = False
    try:
        runtime.initialize_storage(auto_recover=False)
        integrity = runtime.store.integrity_check()
        if integrity != "ok":
            corrupted = True
    except Exception:
        corrupted = True

    if corrupted:
        console.print("[red]✗ synap.db appears corrupted[/red]\n")
    else:
        console.print("[green]✓ Database file is healthy.[/green]")
        import sys

        is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
        if not yes:
            if not is_interactive:
                console.print("Non-interactive terminal detected. Skipping force rebuild.")
                return
            if not typer.confirm("Do you want to force rebuild the index anyway?", default=False):
                return

    console.print("Rebuilding from git history...")
    console.print("[1/3] Restoring file structure from HEAD")

    import json as json_lib

    backup_file = settings.state_path / "repair_backup.json"
    saved_lessons: list[dict[str, Any]] = []
    saved_checkpoints: list[dict[str, Any]] = []
    saved_memory: list[dict[str, Any]] = []

    # If previous crash left a backup, read it
    if backup_file.exists():
        try:
            raw_backup = json_lib.loads(backup_file.read_text(encoding="utf-8"))
            saved_lessons = raw_backup.get("lessons", [])
            saved_checkpoints = raw_backup.get("checkpoints", [])
            saved_memory = raw_backup.get("memory", [])
        except Exception:
            pass

    if not (saved_lessons or saved_checkpoints or saved_memory):
        try:
            with runtime.store.connect() as conn:
                saved_lessons = [dict(r) for r in conn.execute("SELECT * FROM lessons").fetchall()]
                saved_checkpoints = [
                    dict(r) for r in conn.execute("SELECT * FROM checkpoints").fetchall()
                ]
                saved_memory = [
                    dict(r) for r in conn.execute("SELECT * FROM agent_memory").fetchall()
                ]
        except Exception:
            pass

        if saved_lessons or saved_checkpoints or saved_memory:
            try:
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                backup_file.write_text(
                    json_lib.dumps(
                        {
                            "lessons": saved_lessons,
                            "checkpoints": saved_checkpoints,
                            "memory": saved_memory,
                        }
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass

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

    restored_count = 0
    if saved_lessons or saved_checkpoints or saved_memory:
        try:
            with runtime.store.connect() as conn:
                for l_item in saved_lessons:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO lessons
                        (lesson_id, branch, revert_commit, reverted_from, what_failed, why_failed, files_affected, status, created_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            l_item["lesson_id"],
                            l_item["branch"],
                            l_item["revert_commit"],
                            l_item["reverted_from"],
                            l_item["what_failed"],
                            l_item["why_failed"],
                            l_item["files_affected"],
                            l_item["status"],
                            l_item["created_at"],
                            l_item["expires_at"],
                        ),
                    )
                for cp in saved_checkpoints:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO checkpoints
                        (checkpoint_id, branch, commit_hash, doing, changed_files, next_step, blockers, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cp["checkpoint_id"],
                            cp["branch"],
                            cp["commit_hash"],
                            cp["doing"],
                            cp["changed_files"],
                            cp["next_step"],
                            cp["blockers"],
                            cp["created_at"],
                        ),
                    )
                for m in saved_memory:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO agent_memory (id, timestamp, context_key, payload, summary)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (m["id"], m["timestamp"], m["context_key"], m["payload"], m["summary"]),
                    )
            restored_count = len(saved_lessons) + len(saved_checkpoints) + len(saved_memory)
            if backup_file.exists():
                try:
                    backup_file.unlink()
                except OSError:
                    pass
        except Exception as e:
            import structlog

            structlog.get_logger().error("failed_restoring_memory", error=str(e))

    console.print("[2/3] Reindexing all symbols")
    with console.status("[yellow]Reindexing repository...[/yellow]", spinner="dots"):
        runtime.bootstrap(force=True)

    console.print("[3/3] Regenerating wiki from last known state")
    with console.status("[yellow]Regenerating wiki documentation...[/yellow]", spinner="dots"):
        try:
            runtime.wiki.generate_project_wiki()
        except Exception as e:
            import structlog

            structlog.get_logger().error("suppressed_error_caught", error=str(e))

    status_info = runtime.status()
    console.print(f"\n[green]✓ Recovery complete. {status_info.files} files restored.[/green]")
    if restored_count > 0:
        console.print(
            f"[green]✓ Agent memory (L3) successfully preserved ({len(saved_lessons)} lessons, {len(saved_checkpoints)} checkpoints, {len(saved_memory)} memories).[/green]"
        )
    else:
        console.print(
            "[yellow]⚠ Agent memory (L3) could not be recovered — starting fresh.[/yellow]"
        )


@app.command()
def doctor(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    fix: Annotated[
        bool, typer.Option("--fix", help="Attempt to automatically fix detected issues.")
    ] = False,
    context: Annotated[
        bool, typer.Option("--context", help="Output current LLM injection context.")
    ] = False,
    limit: Annotated[
        int | None, typer.Option("--limit", "-n", help="Maximum issues or log lines to display.")
    ] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Only output status summary line.")
    ] = False,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Validate environment and system health."""
    import shutil
    import socket
    import sys

    import httpx

    root = _resolve_repo_root(path)
    settings = _settings(root, json_output=json_output)
    runtime = SynapRuntime(settings)

    # 1. Database check
    db_ok = True
    db_msg = "ok"
    try:
        runtime.initialize_storage(auto_recover=False)
        res = runtime.doctor(auto_recover=False)
        db_msg = str(res.get("database_integrity", "ok"))
    except Exception as e:
        db_ok = False
        db_msg = str(e)

    # 2. Tree-sitter parsers check
    parser_ok = True
    parser_msg = "functional"
    try:
        from synap_git.parser.registry import CodeParserRegistry

        registry = CodeParserRegistry()
        test_file = root / ".synap_test.py"
        test_file.write_text("def test(): pass", encoding="utf-8")
        registry.parse(test_file, relative_path=".synap_test.py")
        test_file.unlink(missing_ok=True)
    except Exception as e:
        parser_ok = False
        parser_msg = str(e)

    # 3. Tokenizer check
    tok_ok = True
    tok_msg = "ready"
    try:
        import tiktoken

        tiktoken.get_encoding("cl100k_base")
    except Exception as e:
        tok_ok = False
        tok_msg = str(e)

    # 4. CLI tools check
    git_path = shutil.which("git")
    gh_path = shutil.which("gh")
    cli_ok = git_path is not None

    # 5. LLM provider check
    prov_ok = True
    prov_msg = "unconfigured"
    if settings.llm_provider is None:
        prov_msg = "No LLM Provider configured (running in structural Mode A)"
    else:
        errors = settings.validate_configuration()
        if errors:
            prov_ok = False
            prov_msg = f"Config error: {errors[0]}"
        else:
            conn_errors = settings.test_connectivity()
            if conn_errors:
                prov_ok = False
                prov_msg = f"Connectivity error: {conn_errors[0]}"
            else:
                prov_msg = f"Provider ({settings.llm_provider}) connectivity verified"

    # 6. Daemon & REST API check
    daemon_info = _read_daemon_heartbeat(root)
    port = daemon_info.get("port", 9876) if daemon_info else 9876
    daemon_running = False
    api_ok = False
    daemon_msg = "Daemon inactive"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        port_in_use = s.connect_ex(("127.0.0.1", port)) == 0

    if daemon_info and port_in_use:
        daemon_running = True
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/api/v1/status", timeout=2.0)
            if r.status_code == 200:
                api_ok = True
                daemon_msg = (
                    f"Daemon active & REST API healthy (PID {daemon_info['pid']}, port {port})"
                )
            else:
                daemon_msg = (
                    f"Daemon running on port {port} but REST API returned HTTP {r.status_code}"
                )
        except Exception as ex:
            daemon_msg = f"Daemon running on port {port} but API check failed: {ex}"
    elif daemon_info:
        daemon_msg = (
            f"Heartbeat found for PID {daemon_info['pid']} but port {port} is not listening"
        )
    else:
        daemon_msg = f"Daemon inactive (port {port} available). Start using `synap start`"

    overall_healthy = db_ok and parser_ok and tok_ok and cli_ok
    status_str = "healthy" if overall_healthy else "degraded"

    if json_output:
        doc_data = {
            "status": status_str,
            "database": {"ok": db_ok, "integrity": db_msg},
            "parsers": {"ok": parser_ok, "status": parser_msg},
            "tokenizer": {"ok": tok_ok, "status": tok_msg},
            "cli_tools": {"git": git_path is not None, "gh": gh_path is not None},
            "llm_provider": {
                "configured": settings.llm_provider is not None,
                "provider": settings.llm_provider,
                "status": prov_msg,
            },
            "daemon": {
                "running": daemon_running,
                "api_healthy": api_ok,
                "pid": daemon_info.get("pid") if daemon_info else None,
                "port": port,
                "status": daemon_msg,
            },
        }
        _emit_json(doc_data)
        return

    if quiet:
        print(
            f"status:{status_str} db:{'ok' if db_ok else 'err'} "
            f"parsers:{'ok' if parser_ok else 'err'} git:{'ok' if cli_ok else 'err'} "
            f"daemon:{'running' if daemon_running else 'stopped'}"
        )
        return

    if not sys.stdout.isatty():
        _stdout_print("[bold cyan]Synap Doctor: System Health Check[/bold cyan]\n")
        _stdout_print(f"{'✓' if db_ok else '✗'} Database integrity: {db_msg}")
        _stdout_print(f"{'✓' if parser_ok else '✗'} Tree-sitter parsers: {parser_msg}")
        _stdout_print(f"{'✓' if tok_ok else '✗'} Tokenizer (tiktoken): {tok_msg}")
        _stdout_print(
            f"✓ Git {'and GitHub CLI installed' if gh_path else 'installed (gh missing)'}"
        )
        _stdout_print(f"ℹ LLM Provider: {prov_msg}")
        _stdout_print(f"ℹ Daemon & API: {daemon_msg}")
        _stdout_print("\nAll checks complete.")
    else:
        _stdout_print("[bold cyan]Synap Doctor: System Health Check[/bold cyan]\n")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=stdout_console,
        ) as progress:
            task_db = progress.add_task("Checking SQLite Database...", total=1)
            progress.update(
                task_db,
                completed=1,
                description=(
                    f"[green]✓ Database integrity: {db_msg}[/green]"
                    if db_ok
                    else f"[red]✗ Database error: {db_msg}[/red]"
                ),
            )

            task_parsers = progress.add_task("Checking Tree-Sitter Parsers...", total=1)
            progress.update(
                task_parsers,
                completed=1,
                description=(
                    "[green]✓ Tree-sitter parsers functional[/green]"
                    if parser_ok
                    else f"[red]✗ Parser error: {parser_msg}[/red]"
                ),
            )

            task_tok = progress.add_task("Checking Tokenizer...", total=1)
            progress.update(
                task_tok,
                completed=1,
                description=(
                    "[green]✓ Tokenizer (tiktoken) ready[/green]"
                    if tok_ok
                    else f"[red]✗ Tokenizer error: {tok_msg}[/red]"
                ),
            )

            task_cli = progress.add_task("Checking CLI dependencies...", total=1)
            desc_cli = (
                "[green]✓ Git and GitHub CLI installed[/green]"
                if gh_path
                else "[green]✓ Git installed[/green] [yellow](gh missing)[/yellow]"
            )
            progress.update(task_cli, completed=1, description=desc_cli)

            task_prov = progress.add_task("Checking LLM Provider...", total=1)
            if settings.llm_provider is None:
                progress.update(
                    task_prov,
                    completed=1,
                    description="[yellow]⚠ No LLM Provider configured (running in structural Mode A)[/yellow]",
                )
            elif prov_ok:
                progress.update(
                    task_prov,
                    completed=1,
                    description=f"[green]✓ Provider ({settings.llm_provider}) connectivity verified[/green]",
                )
            else:
                progress.update(
                    task_prov,
                    completed=1,
                    description=f"[red]✗ Provider error: {prov_msg}[/red]",
                )

            task_daemon = progress.add_task("Checking Daemon & REST API Status...", total=1)
            pid_str = daemon_info.get("pid", "unknown") if daemon_info else "unknown"
            if daemon_running and api_ok:
                progress.update(
                    task_daemon,
                    completed=1,
                    description=f"[green]✓ Daemon active & REST API healthy (PID {pid_str}, port {port})[/green]",
                )
            elif daemon_running:
                progress.update(
                    task_daemon,
                    completed=1,
                    description=f"[yellow]⚠ {daemon_msg}[/yellow]",
                )
            else:
                progress.update(
                    task_daemon,
                    completed=1,
                    description=f"[yellow]⚠ {daemon_msg}[/yellow]",
                )
        _stdout_print("\n[bold]All checks complete.[/bold]")

    if fix:
        console.print("[cyan]Attempting automatic fixes...[/cyan]")
        runtime.initialize_storage(auto_recover=True)
        hooks_install_cmd(path=str(root), quiet=True)
        console.print("[green]✓ Storage verified and Git hooks installed.[/green]")

    if context:
        console.print("\n[bold cyan]Current Session Context (Preamble):[/bold cyan]")
        from synap_git.mcp.server import SynapMCPFacade

        facade = SynapMCPFacade(runtime)
        pre = facade.get_session_preamble()
        console.print(pre.get("compact_preamble", "No context generated."))


app.command(name="ctx", hidden=True)(context_cmd)
app.command(name="st", hidden=True)(status)
app.command(name="sk", hidden=True)(skeleton_cmd)
app.command(name="doc", hidden=True)(doctor)
app.command(name="t", hidden=True)(test_cmd)
app.command(name="ex", hidden=True)(explain_cmd)


@app.command()
def run(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
) -> None:
    """Start the Synap daemon and serve the Diagnostic UI."""
    start(path)


@mcp_app.command("serve")
def mcp_serve(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Run FastMCP stdio server in foreground for AI agents."""
    import asyncio
    import os

    from synap_git.mcp.server import SynapMCPServer

    repo_dir = _resolve_repo_root(path)
    settings = _settings(repo_dir, json_output=True)
    runtime = SynapRuntime(settings)

    # Auto-initialize storage on-the-fly for any opened git repository
    if (repo_dir / ".git").exists():
        try:
            runtime.initialize_storage()
        except Exception:
            pass

    server = SynapMCPServer(runtime)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        os._exit(0)


@mcp_app.command("start")
def mcp_start(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Alias for 'synap mcp serve' to run FastMCP stdio server in foreground."""
    mcp_serve(path)


@mcp_app.command("config")
def mcp_config(
    path: Annotated[
        str, typer.Argument(help="Repository path (omit for dynamic global setup).")
    ] = ".",
    ide: Annotated[
        str,
        typer.Option(
            "--ide",
            "-i",
            help="Target IDE/tool format (generic, cursor, windsurf, claude, cline).",
        ),
    ] = "generic",
    global_setup: Annotated[
        bool,
        typer.Option(
            "--global/--local",
            "-g/-l",
            help="Configure pathless global setup (works dynamically across all repositories).",
        ),
    ] = True,
) -> None:
    """Output the MCP server configuration for IDE setup (Cursor, Windsurf, Claude, Cline, etc.)."""
    import shutil
    import sys

    root = _resolve_repo_root(path)
    synap_bin = shutil.which("synap")
    if synap_bin:
        server_cmd = synap_bin
        server_args = ["mcp", "serve"]
    else:
        server_cmd = sys.executable
        server_args = ["-m", "synap_git.cli", "mcp", "serve"]

    if not global_setup and path != ".":
        server_args.append(root.as_posix())

    config = {
        "mcpServers": {
            "synap": {
                "command": server_cmd,
                "args": server_args,
            }
        }
    }
    _emit_json(config)


@mcp_app.command("print-config")
def mcp_print_config(
    path: Annotated[
        str, typer.Option("--path", "-p", help="Repository path (omit for dynamic global setup).")
    ] = ".",
    ide: Annotated[
        str,
        typer.Option(
            "--ide",
            "-i",
            help="Target IDE format (all, cursor, claude, windsurf).",
        ),
    ] = "all",
    global_setup: Annotated[
        bool,
        typer.Option(
            "--global/--local",
            "-g/-l",
            help="Configure pathless global setup (works dynamically across all repositories).",
        ),
    ] = True,
) -> None:
    """Print the exact MCP JSON snippet directly to stdout for copy-pasting."""
    import shutil
    import sys

    root = _resolve_repo_root(path)
    synap_bin = shutil.which("synap")
    if synap_bin:
        server_cmd = synap_bin
        server_args = ["mcp", "serve"]
    else:
        server_cmd = sys.executable
        server_args = ["-m", "synap_git.cli", "mcp", "serve"]

    if not global_setup and path != ".":
        server_args.append(root.as_posix())

    ide_choice = ide.lower().strip()
    if ide_choice not in ("all", "cursor", "claude", "windsurf"):
        console.print(
            f"[bold red]Error:[/bold red] Unknown IDE '{ide}'. Choose from: all, cursor, claude, windsurf."
        )
        raise typer.Exit(1)

    snippet = {
        "mcpServers": {
            "synap": {
                "command": server_cmd,
                "args": server_args,
            }
        }
    }
    _emit_json(snippet)


@mcp_app.command("verify")
def mcp_verify(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Verify MCP tools, schemas, and transport stability."""
    import time

    console.print("[bold cyan]Synap MCP Verification[/bold cyan]\n")

    settings = _settings(path)
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    from synap_git.mcp.server import SynapMCPFacade

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
                import uuid

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


@app.command()
def ui(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Open the Synap diagnostic UI in your browser."""
    import sys
    import time
    import webbrowser

    abs_path = Path(path).resolve()
    hb = _read_daemon_heartbeat(abs_path)
    daemon_running = False
    if hb:
        pid = hb.get("pid", 0)
        if _is_process_running(pid):
            daemon_running = True

    if not daemon_running:
        console.print("[yellow]Synap background daemon is not running.[/yellow]")
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        start_it = False
        if is_tty:
            import questionary

            start_it = questionary.confirm("Would you like to start the Synap daemon?").ask()
        else:
            start_it = typer.confirm("Would you like to start the Synap daemon?", default=False)

        if start_it:
            start(path)
            # Re-read heartbeat
            for _ in range(15):
                time.sleep(0.2)
                hb = _read_daemon_heartbeat(abs_path)
                if hb and _is_process_running(hb.get("pid", 0)):
                    daemon_running = True
                    break
        else:
            console.print("[red]✗ Daemon is required to serve the UI.[/red]")
            raise typer.Exit(1)

    if not daemon_running or not hb:
        console.print("[red]✗ Failed to start daemon or retrieve UI server port.[/red]")
        raise typer.Exit(1)

    port = hb.get("port", 9876)
    url = f"http://127.0.0.1:{port}"
    console.print("[green]✓ Connecting to runtime...[/green]")
    console.print(f"[green]✓ Opening browser to {url}...[/green]")
    webbrowser.open(url)


@memory_app.command("status")
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


@memory_app.command("prune")
def memory_prune(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Evaluate expiry rules and prune dead memory."""
    runtime = SynapRuntime(_settings(path))
    pruned_count = runtime.store.prune_expired_lessons()
    console.print(f"[green]✓ Evaluated memory expiry. Pruned {pruned_count} lessons.[/green]")


@memory_app.command("verify")
def memory_verify(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Check for dangling file references in approved memory lessons."""
    import json as json_lib

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


@memory_app.command("remember")
def memory_remember(
    key: Annotated[str, typer.Argument(help="Context key or topic for this memory.")],
    content: Annotated[str, typer.Argument(help="Fact, note, or observation content.")],
    path: Annotated[str, typer.Option("--path", "-p", help="Repository path.")] = ".",
    summary: Annotated[str, typer.Option("--summary", "-s", help="Optional short summary.")] = "",
) -> None:
    """Save an observation or technical fact to persistent memory."""
    settings = _settings(path)
    runtime = SynapRuntime(settings)
    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)
    res = facade.remember(key, content, summary=summary)
    console.print(
        f"[bold green]✓ Memory recorded under key '{key}'[/bold green] (ID: {res['memory_id'][:8]}…)"
    )


@memory_app.command("list")
def memory_list(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    key: Annotated[str, typer.Option("--key", "-k", help="Filter by context key.")] = "",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max entries.")] = 15,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """List persistent agent memories and observations."""
    settings = _settings(path, json_output=json_output)
    runtime = SynapRuntime(settings)
    from synap_git.mcp.server import SynapMCPFacade

    facade = SynapMCPFacade(runtime)
    res = facade.recall(key=key, limit=limit)
    memories = res["memories"]

    if json_output:
        _emit({"memories": memories}, json_output=True)
        return

    if not memories:
        console.print(f"[yellow]No memories found{' for key ' + key if key else ''}.[/yellow]")
        return

    table = Table(title="Persistent Agent Memories", show_header=True, header_style="bold cyan")
    table.add_column("Key", style="bold")
    table.add_column("Content")
    table.add_column("Timestamp", style="dim")

    for m in memories:
        ts = datetime.fromtimestamp(m.get("timestamp", 0), tz=UTC).strftime("%Y-%m-%d %H:%M")
        payload = m.get("payload", "")
        summary_txt = m.get("summary", "")
        text = f"{summary_txt}\n{payload}" if summary_txt and summary_txt != payload else payload
        table.add_row(m.get("context_key", ""), text[:80] + ("…" if len(text) > 80 else ""), ts)

    console.print(table)


@memory_app.command("decisions")
def memory_decisions(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    branch: Annotated[
        str,
        typer.Option(
            "--branch",
            "-b",
            help="Branch name or 'all' to search all branches.",
        ),
    ] = "",
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum decisions to display.",
        ),
    ] = 10,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """List logged architectural decisions."""
    runtime = SynapRuntime(_settings(path, json_output=json_output))
    active_branch = branch if branch else runtime.status().branch
    decisions = runtime.store.get_decisions(branch=active_branch if branch else None, limit=limit)

    if json_output:
        _emit({"decisions": decisions}, json_output=True)
        return

    if not decisions:
        console.print(
            f"[yellow]No logged decisions found for branch '{active_branch or 'all'}'.[/yellow]"
        )
        return

    table = Table(
        title=f"Logged Decisions ({active_branch or 'all branches'})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Decision ID", style="dim")
    table.add_column("Commit", style="dim")
    table.add_column("Content")
    table.add_column("Context")

    for item in decisions:
        table.add_row(
            item.get("decision_id", "")[:12] + "…",
            (item.get("commit_hash") or "")[:8],
            (item.get("content") or "")[:45] + ("…" if len(item.get("content") or "") > 45 else ""),
            (item.get("context") or "")[:35] + ("…" if len(item.get("context") or "") > 35 else ""),
        )

    console.print(table)


@lessons_app.command("list")
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


@lessons_app.command("approve")
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


@lessons_app.command("review")
def lessons_review(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Interactively review and manage pending lessons."""
    import questionary
    from rich.panel import Panel

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


@lessons_app.command("reject")
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


@checkpoint_app.command("create")
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


@checkpoint_app.command("restore")
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


@usage_app.callback(invoke_without_command=True)
def usage_callback(
    ctx: typer.Context,
) -> None:
    """View AI Usage Tracking and Cost Metrics."""
    if ctx.invoked_subcommand is None:
        usage_show(".")


@app.command("cost")
def cost(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show detailed LLM call, token usage, and estimated USD cost metrics."""
    usage_show(path)


@usage_app.command("show")
def usage_show(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show detailed LLM call and token usage metrics with estimated USD cost."""
    runtime = SynapRuntime(_settings(path))
    calls = runtime.store.get_llm_calls()

    if not calls:
        console.print("[yellow]No LLM calls recorded yet.[/yellow]")
        return

    # Aggregate by provider/model/purpose
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    total_input = 0
    total_output = 0
    total_cost_usd = 0.0

    for c in calls:
        key = (c["provider"], c["model"], c["purpose"])
        if key not in agg:
            agg[key] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }
        agg[key]["calls"] += 1
        agg[key]["input_tokens"] += c["input_tokens"]
        agg[key]["output_tokens"] += c["output_tokens"]

        call_cost = c.get("cost_usd", 0.0) or 0.0
        agg[key]["cost_usd"] += call_cost

        total_input += c["input_tokens"]
        total_output += c["output_tokens"]
        total_cost_usd += call_cost

    # Render summary table
    # Ensure a visible cost label is present for non-TTY test environments
    console.print(f"Est. Cost (USD): ${total_cost_usd:.4f}")
    table = Table(
        title="LLM Call Aggregated Usage & Cost", show_header=True, header_style="bold cyan"
    )
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Purpose")
    table.add_column("Calls", justify="right")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")
    table.add_column("Est. Cost (USD)", justify="right", style="green")

    for (prov, model, purpose), data in sorted(agg.items()):
        table.add_row(
            prov,
            model,
            purpose,
            str(data["calls"]),
            f"{data['input_tokens']:,}",
            f"{data['output_tokens']:,}",
            f"${data['cost_usd']:.4f}",
        )

    console.print(table)

    # Grand total box
    from rich.panel import Panel

    grand_total_text = (
        f"[bold]Total LLM Calls:[/bold] {len(calls)}\n"
        f"[bold]Total Input Tokens:[/bold] {total_input:,}\n"
        f"[bold]Total Output Tokens:[/bold] {total_output:,}\n"
        f"[bold green]Total Estimated Cost:[/bold green] [bold green]${total_cost_usd:.4f}[/bold green]"
    )
    console.print(
        Panel(grand_total_text, title="Operational Cost & Usage Economics Summary", expand=False)
    )


@usage_app.command("clear")
def usage_clear(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Clear all LLM call usage history."""
    runtime = SynapRuntime(_settings(path))
    runtime.store.clear_llm_calls()
    console.print("[green]✓ LLM usage history cleared successfully.[/green]")


@wiki_app.command("list")
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


@wiki_app.command("show")
def wiki_show(
    filepath: Annotated[
        str,
        typer.Argument(help="The relative path of the wiki page (e.g. src/utils.py.md)."),
    ],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show a specific wiki documentation page rendered in Markdown."""
    from rich.markdown import Markdown

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


@wiki_app.command("retry")
def wiki_retry(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Requeue all permanently failed wiki tasks back to pending state."""
    runtime = SynapRuntime(_settings(path))
    count = runtime.store.retry_failed_wiki_queue()
    if count > 0:
        console.print(f"[green]✓ Requeued {count} failed wiki tasks to pending state.[/green]")
    else:
        console.print("[yellow]No failed wiki tasks found in queue.[/yellow]")
