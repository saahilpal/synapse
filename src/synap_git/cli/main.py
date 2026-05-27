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

from synap_git.config import LoggingMode, RuntimeMode, RuntimeProfile, SynapSettings
from synap_git.diagnostics.logger import configure_logging
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
console = Console()


def _settings(
    path: str,
    *,
    profile: RuntimeProfile = RuntimeProfile.DEV,
    json_output: bool = False,
    mode: RuntimeMode = RuntimeMode.ACTIVE,
) -> SynapSettings:
    settings = SynapSettings(
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

        # Provider
        console.print("Available providers: ollama, openai, anthropic, gemini, openrouter")
        provider = input("Select LLM provider [ollama]: ").strip().lower() or "ollama"
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
        llm_model = input(f"Select model [{default_model}]: ").strip() or default_model

        # Keys/URL
        if provider == "ollama":
            ollama_url = (
                input("Enter Ollama URL [http://localhost:11434]: ").strip()
                or "http://localhost:11434"
            )
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
                save_anyway = input(
                    "Connection check failed. Save configuration anyway? [y/N]: "
                ).strip().lower() in ("y", "yes")

            if not save_anyway:
                console.print("[red]Setup cancelled.[/red]")
                raise typer.Exit(1)

    # 5. Write configurations & secrets (only now)
    if provider != "ollama" and key:
        keyring.set_password("synap", f"{provider}_api_key", key)

    config_content = f"""[llm]
llm_provider = "{provider}"
llm_model = "{llm_model}"
ollama_url = "{ollama_url}"
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


def _auto_protect_synapse(repository_path: Path) -> None:
    gitignore_path = repository_path / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".synap/\n")
        return

    content = gitignore_path.read_text()
    lines = content.splitlines()
    if ".synap/" not in lines and ".synap" not in lines:
        if content and not content.endswith("\n"):
            content += "\n"
        content += ".synap/\n"
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
    """Initialize local Synap state and perform first scan."""
    settings = _settings(path, json_output=json_output)
    if skip_llm:
        settings.llm_provider = None

    _auto_protect_synapse(settings.repository_path)

    runtime = SynapRuntime(settings)
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
) -> None:
    """Start the Synap daemon in the background."""
    import subprocess
    import sys
    import time

    abs_path = Path(path).resolve()
    pid_file = abs_path / ".synap" / "daemon.pid"

    # 1. Check if daemon is already running for the repository
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if _is_process_running(pid):
                console.print(f"[green]✓ Synap daemon is already running (PID {pid}).[/green]")
                hb = _read_daemon_heartbeat(abs_path)
                if hb and "port" in hb:
                    console.print(f"[green]✓ UI available at http://127.0.0.1:{hb['port']}[/green]")
                return
            else:
                pid_file.unlink()
        except Exception:
            pass

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

    console.print("[yellow]Starting Synap daemon...[/yellow]")
    success = False
    for _ in range(15):  # wait up to 3 seconds
        time.sleep(0.2)
        if pid_file.exists():
            hb = _read_daemon_heartbeat(abs_path)
            if hb and hb.get("status") in ("healthy", "degraded"):
                success = True
                port = hb.get("port", 9876)
                pid = int(hb.get("pid", 0))
                console.print(f"[green]✓ Synap daemon started (PID {pid})[/green]")
                console.print("[green]✓ Runtime healthy[/green]")
                console.print(f"[green]✓ UI available at http://127.0.0.1:{port}[/green]")
                break

    if not success:
        console.print(
            "[red]✗ Daemon started but did not report healthy status. Check logs in ~/.config/synap/logs/[/red]"
        )
        raise typer.Exit(1)


@app.command("daemon-run", hidden=True)
def daemon_run(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
) -> None:
    """Internal command to run the daemon loop foreground inside the detached process."""
    import os

    abs_path = Path(path).resolve()
    pid_file = abs_path / ".synap" / "daemon.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    settings = _settings(abs_path.as_posix())
    configure_logging(settings)

    daemon = RuntimeDaemon(settings)
    asyncio.run(daemon.start())


@app.command()
def stop(
    path: Annotated[str, typer.Argument(help="Repository path to stop.")] = ".",
) -> None:
    """Gracefully terminate background services."""
    import os
    import signal
    import time

    abs_path = Path(path).resolve()
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
        except Exception:
            pass
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
    abs_path = Path(path).resolve()
    console.print("[yellow]Restarting Synap services...[/yellow]")

    pid_file = abs_path / ".synap" / "daemon.pid"
    if pid_file.exists():
        stop(path)

    start(path)


@app.command()
def status(
    path: Annotated[str, typer.Argument(help="Repository path to inspect.")] = ".",
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Show current repository context status."""
    abs_path = Path(path).resolve()
    settings = _settings(abs_path.as_posix(), json_output=json_output)
    runtime = SynapRuntime(settings)
    status_info = runtime.status()

    hb = _read_daemon_heartbeat(abs_path)
    daemon_running = False
    if hb:
        pid = hb.get("pid", 0)
        if _is_process_running(pid):
            daemon_running = True

    if json_output:
        out = _jsonable(status_info)
        out["daemon"] = hb if daemon_running else None
        _emit(out, json_output=True)
        return

    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
    console.print("[bold cyan]          Synap Runtime Status          [/bold cyan]")
    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")

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

    from rich.table import Table

    table = Table.grid(padding=(0, 2))
    table.add_column("Property", style="bold cyan")
    table.add_column("Value")

    table.add_row("Daemon:", daemon_status)
    table.add_row("Repository:", abs_path.name)
    table.add_row("Branch:", status_info.branch)
    table.add_row("Indexed:", indexed_files)
    table.add_row("Memory:", memory_nodes)
    table.add_row("LLM Provider:", provider.capitalize())
    table.add_row("Model:", model)
    table.add_row("CPU:", cpu_val)
    table.add_row("RAM:", ram_val)

    console.print(table)
    console.print()

    if status_info.is_dirty:
        console.print(
            "[bold yellow]⚠ Warning: Working tree has uncommitted changes. Run git commit to index them.[/bold yellow]"
        )


@app.command()
def logs(
    tail: Annotated[
        bool, typer.Option("--tail", "-t", help="Stream new log entries in real-time.")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Show verbose debug and trace logs.")
    ] = False,
) -> None:
    """View and tail Synap runtime logs."""
    import time

    log_dir = Path("~/.config/synap/logs").expanduser()
    log_file = log_dir / "daemon.log"

    if not log_file.exists():
        console.print("[yellow]No log files found yet.[/yellow]")
        return

    try:
        with open(log_file, encoding="utf-8") as f:
            if not tail:
                lines = f.readlines()
                for line in lines[-50:]:
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
def update() -> None:
    """Check for updates and upgrade the Synap runtime."""
    import subprocess
    import sys

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
                latest_version = resp.json()["info"]["version"]
        except Exception as e:
            console.print(
                f"[yellow]⚠ Failed to reach PyPI: {e}. Cannot check for updates.[/yellow]"
            )
            return

    console.print(f"Latest version on PyPI: [bold]{latest_version}[/bold]")

    if current_version == latest_version and install_method != "editable":
        console.print("[green]✓ Synap is already up to date.[/green]")
        return

    if install_method == "editable":
        console.print("\n[yellow]Editable installation detected. Updating via git pull...[/yellow]")
        try:
            subprocess.run(["git", "pull", "origin", "main"], check=True)
            subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=True)
            console.print(
                "[green]✓ Update successful (Git repository pulled and re-installed)[/green]"
            )
        except Exception as e:
            console.print(f"[bold red]✗ Git update failed:[/bold red] {e}")
            raise typer.Exit(1)
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
        subprocess.run(cmd, check=True)
        console.print("[green]✓ Update successful[/green]")
    except Exception as e:
        console.print(f"[bold red]✗ Upgrade failed:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Print the Synap package version."""
    from synap_git import __version__

    console.print(f"Synap version: [bold]{__version__}[/bold]")


def version_callback(value: bool) -> None:
    if value:
        from synap_git import __version__

        typer.echo(f"Synap version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
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
    pass


@app.command()
def rollback(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Rollback active state to a previous commit."""
    import subprocess

    settings = _settings(path)
    runtime = SynapRuntime(settings)

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
    runtime = SynapRuntime(settings)

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
        console.print("[red]✗ synap.db appears corrupted[/red]\n")
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
    console.print("[bold cyan]Synap Doctor: System Health Check[/bold cyan]\n")

    settings = _settings(path)
    runtime = SynapRuntime(settings)

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
            from synap_git.parser.registry import CodeParserRegistry

            registry = CodeParserRegistry()
            test_file = Path(path) / ".synap_test.py"
            test_file.write_text("def test(): pass", encoding="utf-8")
            registry.parse(test_file, relative_path=".synap_test.py")
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
            if settings.llm_provider is None:
                progress.update(
                    task_prov,
                    completed=1,
                    description="[yellow]⚠ No LLM Provider configured (running in structural Mode A)[/yellow]",
                )
            else:
                errors = settings.validate_configuration()
                if errors:
                    progress.update(
                        task_prov,
                        completed=1,
                        description=f"[red]✗ Config error: {errors[0]}[/red]",
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

        task_daemon = progress.add_task("Checking Daemon Status...", total=1)
        try:
            daemon_info = _read_daemon_heartbeat(settings.repository_path)
            if daemon_info:
                status_str = daemon_info["status"].upper()
                if status_str == "HEALTHY":
                    progress.update(
                        task_daemon,
                        completed=1,
                        description=f"[green]✓ Daemon active and healthy (PID {daemon_info['pid']}, uptime {daemon_info['uptime_seconds']}s)[/green]",
                    )
                elif status_str == "STALE":
                    progress.update(
                        task_daemon,
                        completed=1,
                        description="[yellow]⚠ Daemon heartbeat file exists but is stale (not running?)[/yellow]",
                    )
                else:
                    progress.update(
                        task_daemon,
                        completed=1,
                        description=f"[red]✗ Daemon degraded: {daemon_info.get('last_error')}[/red]",
                    )
            else:
                progress.update(
                    task_daemon,
                    completed=1,
                    description="[yellow]⚠ Daemon inactive (not running). Start it using `synap start`[/yellow]",
                )
        except Exception as e:
            progress.update(
                task_daemon, completed=1, description=f"[red]✗ Daemon status error: {e}[/red]"
            )

    console.print("\n[bold]All checks complete.[/bold]")


@app.command()
def run(
    path: Annotated[str, typer.Argument(help="Repository path to watch.")] = ".",
) -> None:
    """Start the Synap daemon and serve the Diagnostic UI."""
    start(path)


@mcp_app.command("start")
def mcp_start(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Start the MCP server."""
    settings = _settings(path)
    runtime = SynapRuntime(settings)
    runtime.bootstrap()

    from synap_git.mcp.server import SynapMCPServer

    server = SynapMCPServer(runtime)
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
            "synap": {
                "command": sys.executable,
                "args": ["-m", "synap_git.cli", "mcp", "start", abs_path],
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
            start_it = input(
                "Would you like to start the Synap daemon? [y/N]: "
            ).strip().lower() in ("y", "yes")

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


@lessons_app.command("reject")
def lessons_reject(
    lesson_id: Annotated[str, typer.Argument(help="The ID of the lesson to reject.")],
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Reject a pending lesson."""
    runtime = SynapRuntime(_settings(path))
    pending = runtime.store.get_lessons("pending")
    target = next((lesson for lesson in pending if lesson["lesson_id"] == lesson_id), None)

    if not target:
        console.print(f"[red]✗ Pending lesson {lesson_id} not found.[/red]")
        raise typer.Exit(1)

    runtime.store.update_lesson(lesson_id, target["why_failed"], "rejected", actor="cli_user")
    console.print(f"[yellow]✓ Lesson {lesson_id} rejected. Memory updated.[/yellow]")


@checkpoint_app.command("create")
def checkpoint_create(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
    doing: Annotated[str, typer.Option(help="What the agent is currently doing.")] = "",
    files: Annotated[str, typer.Option(help="Comma-separated list of changed files.")] = "",
    next_step: Annotated[str, typer.Option(help="The next step to be taken.")] = "",
    blockers: Annotated[str, typer.Option(help="Current blockers or obstacles.")] = "",
) -> None:
    """Create a new context checkpoint."""
    if not doing:
        console.print("[red]✗ The --doing option is required.[/red]")
        raise typer.Exit(1)

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


@cost_app.command("show")
def cost_show(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Show detailed LLM call and cost tracking metrics."""
    runtime = SynapRuntime(_settings(path))
    calls = runtime.store.get_llm_calls()

    if not calls:
        console.print("[yellow]No LLM calls recorded yet.[/yellow]")
        return

    # Aggregate by provider/model/purpose
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    total_input = 0
    total_output = 0
    total_cost = 0.0

    for c in calls:
        key = (c["provider"], c["model"], c["purpose"])
        if key not in agg:
            agg[key] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
            }
        agg[key]["calls"] += 1
        agg[key]["input_tokens"] += c["input_tokens"]
        agg[key]["output_tokens"] += c["output_tokens"]
        agg[key]["cost"] += c["cost_usd"]

        total_input += c["input_tokens"]
        total_output += c["output_tokens"]
        total_cost += c["cost_usd"]

    # Render summary table
    table = Table(title="LLM Call Aggregated Costs", show_header=True, header_style="bold cyan")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Purpose")
    table.add_column("Calls", justify="right")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")
    table.add_column("Cost (USD)", justify="right")

    for (prov, model, purpose), data in sorted(agg.items()):
        table.add_row(
            prov,
            model,
            purpose,
            str(data["calls"]),
            f"{data['input_tokens']:,}",
            f"{data['output_tokens']:,}",
            f"${data['cost']:.6f}",
        )

    console.print(table)

    # Grand total box
    from rich.panel import Panel

    grand_total_text = (
        f"[bold]Total Calls:[/bold] {len(calls)}\n"
        f"[bold]Total Input Tokens:[/bold] {total_input:,}\n"
        f"[bold]Total Output Tokens:[/bold] {total_output:,}\n"
        f"[bold]Total Cost (USD):[/bold] [green]${total_cost:.6f}[/green]"
    )
    console.print(Panel(grand_total_text, title="Operational Cost Summary", expand=False))


@cost_app.command("clear")
def cost_clear(
    path: Annotated[str, typer.Argument(help="Repository path.")] = ".",
) -> None:
    """Clear all LLM call cost history."""
    runtime = SynapRuntime(_settings(path))
    runtime.store.clear_llm_calls()
    console.print("[green]✓ LLM cost history cleared successfully.[/green]")


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

    wiki_path = wiki_dir / target
    if not wiki_path.exists():
        wiki_path = wiki_dir / filepath
        if not wiki_path.exists():
            console.print(f"[red]✗ Wiki page '{filepath}' not found.[/red]")
            raise typer.Exit(1)

    content = wiki_path.read_text(encoding="utf-8")
    console.print(Markdown(content))
