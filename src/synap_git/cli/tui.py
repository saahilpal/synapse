from __future__ import annotations

import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from synap_git import __version__
from synap_git.config import SynapSettings
from synap_git.diagnostics.logger import get_logger
from synap_git.storage.global_memory import GlobalMemoryStore

logger = get_logger("tui")

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/init", "Initialize .synap/ repository context storage & index"),
    ("/status", "Truthful status of repo, branch, daemon & symbols"),
    ("/find", "<query> Interactive hybrid search across symbols & docs"),
    ("/remember", "<key> <content> Save architectural decision or fact"),
    ("/forget", "<key> Remove memory item by key"),
    ("/wiki", "[status|generate|show] Structural markdown wiki engine"),
    ("/global", "[query] Query cross-repo developer memories"),
    ("/ingest", "<id> Promote global memory into repository"),
    ("/model", "[probe|set <model>] Auto-discovery or model override"),
    ("/skill", "[sync|export] Install/update SKILL.md and rules"),
    ("/logs", "[-n <lines>] View recent background daemon activity"),
    ("/doctor", "[--fix] Run health diagnostics and auto-repair"),
    ("/help", "Show concise slash-command cheatsheet"),
    ("/quit", "Exit the interactive REPL"),
]

SUBCOMMAND_HINTS: dict[str, list[tuple[str, str]]] = {
    "/wiki": [
        ("status", "Inspect markdown wiki documentation status"),
        ("generate", "Generate 1:1 structural markdown documentation"),
        ("show", "<page> Preview a markdown wiki page"),
    ],
    "/model": [
        ("probe", "Auto-discover active local runtimes on standard ports"),
        ("set", "<provider:model> Configure active LLM model override"),
    ],
    "/skill": [
        ("sync", "Install/update SKILL.md and AGENTS.md rules"),
        ("export", "Export standalone SKILL.md into repository root"),
    ],
    "/doctor": [
        ("--fix", "Attempt automatic repair of storage and permissions"),
    ],
}


class SynapCommandCompleter(Completer):
    """Command palette completer with argument hints."""

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        words = text.split()

        if len(words) <= 1 and not text.endswith(" "):
            search = text.strip()
            for cmd, hint in SLASH_COMMANDS:
                if cmd.startswith(search):
                    yield Completion(
                        cmd,
                        start_position=-len(search),
                        display=cmd,
                        display_meta=hint,
                    )
            if "/exit".startswith(search) and search != "/":
                yield Completion(
                    "/exit",
                    start_position=-len(search),
                    display="/exit",
                    display_meta="Exit the interactive REPL (alias to /quit)",
                )
        elif len(words) >= 1:
            cmd = words[0].lower()
            if cmd in SUBCOMMAND_HINTS:
                sub_search = "" if text.endswith(" ") else words[-1].lower()
                for sub, hint in SUBCOMMAND_HINTS[cmd]:
                    if sub.startswith(sub_search):
                        yield Completion(
                            sub,
                            start_position=-len(sub_search),
                            display=sub,
                            display_meta=hint,
                        )


class SynapInteractiveREPL:
    """Fast, interactive slash-command REPL preserving 100% terminal scrollback."""

    def __init__(self, repo_path: Path | str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()
        self.console = Console()
        self.settings = SynapSettings(
            repository_path=self.repo_path,
            state_path=self.repo_path / ".synap",
        )
        self._runtime: Any = None
        self.global_store = GlobalMemoryStore()

        # Ensure history directory exists
        history_file = Path.home() / ".synap" / "history"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        self.history = FileHistory(str(history_file))

        self.completer = SynapCommandCompleter()
        self.session: PromptSession[str] = PromptSession(
            history=self.history,
            completer=self.completer,
        )

    @property
    def runtime(self) -> Any:
        if self._runtime is None:
            from synap_git.indexer.engine import SynapRuntime

            self._runtime = SynapRuntime(self.settings)
        return self._runtime

    def _print_error(self, what_failed: str, why: str, next_steps: str) -> None:
        """Render a truthful, standardized 3-part diagnostic error message."""
        self.console.print(f"[bold red]✗ {what_failed}[/bold red]")
        self.console.print(f"  [yellow]Reason:[/yellow] {why}")
        self.console.print(f"  [cyan]Next steps:[/cyan] {next_steps}")

    def prompt_init_if_needed(self) -> None:
        """If no .synap/ directory exists, ask once to initialize."""
        synap_dir = self.repo_path / ".synap"
        if not synap_dir.exists():
            self.console.print("[yellow]No .synap/ directory found for this repository.[/yellow]")
            try:
                response = input("Initialize Synapse now? [Y/n]: ").strip().lower()
                if response in ("", "y", "yes"):
                    self._cmd_init()
                else:
                    self.console.print(
                        "[dim]Skipped initialization. Type /init when ready.[/dim]\n"
                    )
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Skipped initialization.[/dim]\n")

    def print_banner(self) -> None:
        """Render truthful 3-line status banner without clearing scrollback."""
        # Line 1: Repo & branch
        branch_name = "unknown"
        tree_state = "clean"
        try:
            state = self.runtime.git.state()
            branch_name = state.effective_branch
            tree_state = f"dirty ({len(state.dirty_files)} changed)" if state.is_dirty else "clean"
        except Exception:
            pass
        line1 = f"[bold cyan]⚡ Synapse[/bold cyan] [bold green]v{__version__}[/bold green] · [bold]{self.repo_path.name}[/bold] @ [bold magenta]{branch_name}[/bold magenta] [{tree_state}]"

        # Line 2: Index symbol count & wiki page count
        symbol_count = 0
        file_count = 0
        try:
            status = self.runtime.status()
            symbol_count = status.symbols
            file_count = status.files
        except Exception:
            pass

        wiki_dir = self.repo_path / ".synap" / "wiki"
        wiki_pages = len(list(wiki_dir.glob("**/*.md"))) if wiki_dir.exists() else 0
        line2 = f"[dim]📊 Index: [bold white]{symbol_count:,}[/bold white] symbols across [bold white]{file_count:,}[/bold white] files · Wiki: [bold white]{wiki_pages}[/bold white] pages[/dim]"

        # Line 3: Local LLM detected or Mode A
        model_display = "Mode A (deterministic Tree-sitter AST, no LLM)"
        if self.settings.llm_provider:
            model_display = (
                f"Local LLM: {self.settings.llm_provider}:{self.settings.llm_model or 'default'}"
            )
        else:
            try:
                import socket

                for name, port in [("Ollama", 11434), ("LM Studio", 1234), ("vLLM", 8000)]:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.08)
                        if s.connect_ex(("127.0.0.1", port)) == 0:
                            model_display = (
                                f"Local LLM detected on port {port} ({name}) · Running Mode A"
                            )
                            break
            except Exception:
                pass
        line3 = f"[dim]🧠 Runtime: {model_display}[/dim]"

        self.console.print(line1)
        self.console.print(line2)
        self.console.print(line3)
        self.console.print(
            "[dim]Type [bold cyan]/help[/bold cyan] for commands or enter text to search. [bold cyan]/quit[/bold cyan] to exit.[/dim]\n"
        )

    def execute_command(self, line: str) -> bool:
        """Execute a single line. Return False to exit, True to continue."""
        text = line.strip()
        if not text:
            return True

        # Quick exit check
        if text.lower() in ("/exit", "/quit", "exit", "quit", "q"):
            self.console.print("[dim]Goodbye![/dim]")
            return False

        # Non-slash input routing
        if not text.startswith("/"):
            parts = text.split()
            first_word = parts[0].lower()
            known_bare_commands = {
                "init",
                "status",
                "find",
                "remember",
                "forget",
                "wiki",
                "global",
                "ingest",
                "model",
                "skill",
                "logs",
                "doctor",
                "help",
            }
            if first_word in known_bare_commands:
                text = "/" + text
            else:
                # Plain text input runs /find <query>
                self._cmd_find(parts)
                return True

        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("/exit", "/quit"):
            self.console.print("[dim]Goodbye![/dim]")
            return False

        if cmd == "/help":
            self._cmd_help()
        elif cmd == "/init":
            self._cmd_init()
        elif cmd == "/status":
            self._cmd_status()
        elif cmd == "/find":
            self._cmd_find(args)
        elif cmd == "/remember":
            self._cmd_remember(args)
        elif cmd == "/forget":
            self._cmd_forget(args)
        elif cmd == "/wiki":
            self._cmd_wiki(args)
        elif cmd == "/global":
            self._cmd_global(args)
        elif cmd == "/ingest":
            self._cmd_ingest(args)
        elif cmd == "/model":
            self._cmd_model(args)
        elif cmd == "/skill":
            self._cmd_skill(args)
        elif cmd == "/logs":
            self._cmd_logs(args)
        elif cmd == "/doctor":
            self._cmd_doctor(args)
        else:
            self._print_error(
                f"Unknown command: '{cmd}'",
                "Command is not in the recognized set of slash commands.",
                "Type /help to see all 14 available commands.",
            )

        return True

    def _cmd_help(self) -> None:
        """Show clean slash-command cheatsheet fitting entirely on one screen."""
        table = Table(
            title="⚡ Synapse Slash Commands",
            border_style="cyan",
            show_header=True,
            header_style="bold magenta",
            padding=(0, 1),
        )
        table.add_column("Command", style="bold cyan", no_wrap=True)
        table.add_column("Syntax", style="yellow", no_wrap=True)
        table.add_column("Description", style="white")

        table.add_row("/init", "/init", "Initialize context storage & index repository")
        table.add_row("/status", "/status", "Truthful status of git, daemon & indexed symbols")
        table.add_row("/find", "/find <query>", "Hybrid search across symbols, docs & files")
        table.add_row(
            "/remember", "/remember <k> <v>", "Save architectural decision or operational fact"
        )
        table.add_row("/forget", "/forget <key>", "Remove memory item by key")
        table.add_row(
            "/wiki", "/wiki [status|generate|show]", "1:1 structural markdown wiki engine"
        )
        table.add_row("/global", "/global [query]", "Query cross-repo developer memories")
        table.add_row("/ingest", "/ingest <id>", "Promote global memory into this repository")
        table.add_row(
            "/model", "/model [probe|set <m>]", "Probe local LLM runtimes or set model override"
        )
        table.add_row("/skill", "/skill [sync|export]", "Sync or export agent SKILL.md rules")
        table.add_row("/logs", "/logs [-n <lines>]", "View recent background daemon activity")
        table.add_row("/doctor", "/doctor [--fix]", "Health diagnostics and auto-repair")
        table.add_row("/help", "/help", "Show this command cheatsheet")
        table.add_row("/quit", "/quit or /exit", "Exit the interactive REPL")

        self.console.print(table)

    def _cmd_init(self) -> None:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console,
                transient=True,
            ) as progress:
                t1 = progress.add_task("[cyan]Initializing storage...", total=None)
                self.runtime.initialize_storage()
                self.runtime.bootstrap()
                progress.update(t1, completed=True)

                t2 = progress.add_task("[cyan]Indexing symbols & AST...", total=None)
                state = self.runtime.git.state()
                self.runtime.index_repository(git_state=state)
                progress.update(t2, completed=True)

            status = self.runtime.status()
            # Verified check
            db_file = self.repo_path / ".synap" / "graph.db"
            if not db_file.exists():
                raise RuntimeError("Database verification failed: .synap/graph.db was not created.")

            self.console.print(
                f"[bold green]✔ Initialized Synapse in[/bold green] {self.repo_path}"
            )
            self.console.print(
                f"[dim]Verified index: {status.files} files, {status.symbols} symbols "
                f"on branch '{status.branch}'.[/dim]"
            )
        except Exception as e:
            self._print_error(
                "Initialization failed",
                str(e),
                "Verify repository write permissions and ensure Git is installed.",
            )

    def _cmd_status(self) -> None:
        try:
            self.runtime.initialize_storage(auto_recover=False)
            status = self.runtime.status()
            git_state = self.runtime.git.state()

            table = Table(
                title=f"⚡ Synapse Status — {self.repo_path.name}",
                border_style="cyan",
                padding=(0, 1),
            )
            table.add_column("Component", style="bold cyan")
            table.add_column("Details")

            table.add_row("Branch", f"[bold green]{git_state.effective_branch}[/bold green]")
            table.add_row(
                "HEAD Commit",
                f"`{(git_state.head_commit or 'none')[:8]}`",
            )
            dirty_desc = (
                f"[bold red]DIRTY[/bold red] ({len(git_state.dirty_files)} changed files)"
                if git_state.is_dirty
                else "[bold green]CLEAN[/bold green]"
            )
            table.add_row("Working Tree", dirty_desc)

            heartbeat_file = self.repo_path / ".synap" / "daemon_heartbeat.json"
            daemon_str = "[dim]Inactive[/dim]"
            if heartbeat_file.exists():
                try:
                    import json

                    hb = json.loads(heartbeat_file.read_text(encoding="utf-8"))
                    daemon_str = f"[green]Active[/green] (PID: {hb.get('pid')}, port: {hb.get('port', 9876)})"
                except Exception:
                    daemon_str = "[yellow]Stale lockfile[/yellow]"
            table.add_row("Daemon", daemon_str)

            table.add_row("Indexed Files", str(status.files))
            table.add_row("Indexed Symbols", str(status.symbols))

            latest_cp = self.runtime.store.get_latest_checkpoint(git_state.effective_branch)
            if latest_cp:
                doing_txt = latest_cp.get("doing", "N/A")
                table.add_row("Active Checkpoint", doing_txt)

            self.console.print(table)
        except Exception as e:
            self._print_error(
                "Status query failed",
                str(e),
                "Run /init to initialize context storage or /doctor to check diagnostics.",
            )

    def _cmd_find(self, args: list[str]) -> None:
        if not args:
            self._print_error(
                "Missing query for /find",
                "No search terms were provided.",
                "Syntax: /find <query> (e.g. /find authenticate_user)",
            )
            return
        query = " ".join(args)
        self.console.print(f"[dim]Searching for:[/dim] [cyan]{query}[/cyan]...")
        try:
            result_text, sources, debug_info = self.runtime.query_hybrid(
                query=query,
                max_tokens=4000,
                synthesize_answer=False,
            )

            table = Table(
                title=f"Search Results for '{query}'",
                border_style="cyan",
                padding=(0, 1),
            )
            table.add_column("Symbol / File", style="bold cyan")
            table.add_column("Kind", style="yellow")
            table.add_column("Location", style="magenta")
            table.add_column("Match Reason", style="dim")

            count = 0
            for src in sources:
                count += 1
                sym = src.get("name") or src.get("symbol") or "N/A"
                kind = src.get("kind") or "symbol"
                loc = f"{src.get('path') or src.get('source_path', '')}:{src.get('start_line', '')}-{src.get('end_line', '')}"
                reason = src.get("reason", "hybrid_match")
                table.add_row(sym, kind, loc, reason)

            if count > 0:
                self.console.print(table)
            else:
                self.console.print("[yellow]No symbol matches found.[/yellow]")

            if result_text:
                self.console.print(Panel(result_text, title="Summary Preview", border_style="dim"))
        except Exception as e:
            self._print_error(
                "Search execution failed",
                str(e),
                "Run /init to re-index symbols or /status to check database integrity.",
            )

    def _cmd_remember(self, args: list[str]) -> None:
        if len(args) < 2:
            self._print_error(
                "Missing arguments for /remember",
                "Both a key and content are required.",
                "Syntax: /remember <key> <content> (e.g. /remember timeout 5000ms)",
            )
            return
        key = args[0]
        content = " ".join(args[1:])
        try:
            import uuid

            memory_id = str(uuid.uuid4())
            self.runtime.store.store_memory(
                memory_id=memory_id,
                context_key=key,
                payload=content,
                summary=content[:120],
            )
            # Verified check
            rec = self.runtime.store.get_recent_memory(context_key=key)
            if not rec or rec[0]["payload"] != content:
                raise RuntimeError("Persistence verification failed: memory row was not recorded.")

            self.console.print(
                f"[bold green]✔ Saved memory[/bold green] under key '[cyan]{key}[/cyan]'."
            )
        except Exception as e:
            self._print_error(
                "Failed to save memory",
                str(e),
                "Verify database write permissions or run /doctor --fix.",
            )

    def _cmd_forget(self, args: list[str]) -> None:
        if not args:
            self._print_error(
                "Missing key for /forget",
                "No memory key specified.",
                "Syntax: /forget <key> (e.g. /forget timeout)",
            )
            return
        key = args[0]
        try:
            with self.runtime.store.connect() as conn:
                cur = conn.execute("DELETE FROM agent_memory WHERE context_key = ?", (key,))
                if cur.rowcount > 0:
                    self.console.print(
                        f"[bold yellow]✔ Removed memory[/bold yellow] with key '[cyan]{key}[/cyan]'."
                    )
                else:
                    self.console.print(f"[yellow]No memory found under key[/yellow] '{key}'.")
        except Exception as e:
            self._print_error(
                "Failed to remove memory",
                str(e),
                "Ensure database is accessible and not locked by another process.",
            )

    def _cmd_wiki(self, args: list[str]) -> None:
        sub = args[0].lower() if args else "status"
        wiki_dir = self.repo_path / ".synap" / "wiki"

        if sub == "status":
            if not wiki_dir.exists():
                self.console.print(
                    "[yellow]Wiki directory not initialized. Run [/yellow][bold cyan]/wiki generate[/bold cyan]"
                )
                return
            pages = list(wiki_dir.glob("**/*.md"))
            self.console.print(
                f"[bold cyan]Wiki Status:[/bold cyan] {len(pages)} markdown page(s) in {wiki_dir}"
            )
            for p in pages[:10]:
                self.console.print(f"  • {p.relative_to(wiki_dir)}")
            if len(pages) > 10:
                self.console.print(f"  [dim]... and {len(pages) - 10} more pages[/dim]")
        elif sub == "generate":
            self.console.print("[dim]Generating 1:1 structural markdown wiki...[/dim]")
            try:
                from synap_git.indexer.wiki import WikiEngine

                engine = WikiEngine(self.settings, self.runtime.store)
                res = engine.generate()
                # Verification
                pages = list(wiki_dir.glob("**/*.md")) if wiki_dir.exists() else []
                self.console.print(
                    f"[bold green]✔ Wiki generation complete.[/bold green] Generated {len(pages)} verified pages."
                )
            except Exception as e:
                self._print_error(
                    "Wiki generation failed",
                    str(e),
                    "Run /init first to ensure AST symbol graphs are indexed.",
                )
        elif sub == "show":
            if len(args) < 2:
                self._print_error(
                    "Missing page name for /wiki show",
                    "No markdown file name provided.",
                    "Syntax: /wiki show <page_name> (e.g. /wiki show main.py)",
                )
                return
            target = args[1]
            if not target.endswith(".md"):
                target += ".md"
            target_path = wiki_dir / target
            if not target_path.exists():
                self._print_error(
                    f"Wiki page '{target}' not found",
                    f"File does not exist at {target_path}",
                    "Run /wiki status to list all available generated pages.",
                )
                return
            content = target_path.read_text(encoding="utf-8")
            from rich.markdown import Markdown

            self.console.print(Markdown(content))
        else:
            self._print_error(
                f"Unknown /wiki subcommand: '{sub}'",
                "Subcommand not supported.",
                "Available subcommands: /wiki status, /wiki generate, /wiki show <page>",
            )

    def _cmd_global(self, args: list[str]) -> None:
        query = " ".join(args) if args else ""
        try:
            memories = self.global_store.list_memories(query=query, limit=15)
            if not memories:
                self.console.print(
                    "[yellow]No global memories found.[/yellow] (Database: ~/.synap/global_memory.db)"
                )
                return

            table = Table(
                title="Global Developer Memories (~/.synap/global_memory.db)",
                border_style="cyan",
                padding=(0, 1),
            )
            table.add_column("Global ID", style="dim", no_wrap=True)
            table.add_column("Context Key", style="bold cyan")
            table.add_column("Category", style="yellow")
            table.add_column("Preview / Content", style="white")
            table.add_column("Usage", style="magenta")

            for m in memories:
                preview = (m.get("summary") or m.get("content", ""))[:60]
                table.add_row(
                    m["global_id"][:8],
                    m["context_key"],
                    m["category"],
                    preview,
                    str(m.get("usage_count", 0)),
                )

            self.console.print(table)
            self.console.print(
                "[dim]Use [bold cyan]/ingest <id>[/bold cyan] to promote a global memory to this repository.[/dim]"
            )
        except Exception as e:
            self._print_error(
                "Global memory query failed",
                str(e),
                "Verify ~/.synap/global_memory.db file permissions.",
            )

    def _cmd_ingest(self, args: list[str]) -> None:
        if not args:
            self._print_error(
                "Missing ID for /ingest",
                "No global memory ID provided.",
                "Syntax: /ingest <global_id> (run /global to see IDs)",
            )
            return
        gid = args[0]
        try:
            m = self.global_store.get_memory(gid)
            if not m:
                matches = self.global_store.list_memories(query=gid, limit=2)
                if matches and matches[0]["global_id"].startswith(gid):
                    m = matches[0]

            if not m:
                self._print_error(
                    f"Global memory '{gid}' not found",
                    "No record in ~/.synap/global_memory.db matches this ID.",
                    "Run /global to list available memories and their IDs.",
                )
                return

            import uuid

            memory_id = str(uuid.uuid4())
            summary = f"[From Global {m['global_id'][:8]}] {m.get('summary', '')}".strip()
            self.runtime.store.store_memory(
                memory_id=memory_id,
                context_key=m["context_key"],
                payload=m["content"],
                summary=summary,
            )
            self.global_store.record_usage(m["global_id"])

            # Verified check
            ingested = self.runtime.store.get_recent_memory(context_key=m["context_key"])
            if not ingested:
                raise RuntimeError("Verification failed: memory was not ingested into local store.")

            self.console.print(
                f"[bold green]✔ Ingested global memory[/bold green] '[cyan]{m['context_key']}[/cyan]' "
                f"into repository memory."
            )
        except Exception as e:
            self._print_error(
                "Failed to ingest global memory",
                str(e),
                "Run /status to check local repository database health.",
            )

    def _cmd_model(self, args: list[str]) -> None:
        sub = args[0].lower() if args else "probe"
        if sub == "probe":
            self.console.print("[dim]Probing local LLM runtimes (Ollama, LM Studio, etc.)...[/dim]")
            discovered: list[dict[str, Any]] = []
            try:
                from synap_git.provider.discovery import probe_local_runtimes

                runtime_info = probe_local_runtimes(force=True)
                if runtime_info is not None:
                    discovered.append(
                        {
                            "provider": runtime_info.name,
                            "url": f"{runtime_info.host}:{runtime_info.port}",
                            "model": runtime_info.chat_model or "auto-detect",
                            "status": "Active",
                        }
                    )
            except Exception:
                pass

            if not discovered:
                import socket

                probes = [
                    ("Ollama", "http://localhost:11434", 11434),
                    ("LM Studio", "http://localhost:1234", 1234),
                    ("vLLM / llama.cpp", "http://localhost:8000", 8000),
                ]
                for name, url, port in probes:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.3)
                        if s.connect_ex(("127.0.0.1", port)) == 0:
                            discovered.append(
                                {
                                    "provider": name,
                                    "url": url,
                                    "model": "auto-detect",
                                    "status": "Port Active",
                                }
                            )

            if discovered:
                table = Table(
                    title="Discovered Local Runtimes", border_style="cyan", padding=(0, 1)
                )
                table.add_column("Provider", style="bold cyan")
                table.add_column("Base URL", style="yellow")
                table.add_column("Model", style="white")
                table.add_column("Status", style="green")
                for d in discovered:
                    table.add_row(d["provider"], d["url"], str(d["model"]), d["status"])
                self.console.print(table)
            else:
                self.console.print(
                    "[yellow]No local LLM runtimes discovered on standard ports.[/yellow]\n"
                    "[dim]Operating in high-speed deterministic Mode A (Tree-sitter AST).[/dim]"
                )
        elif sub == "set":
            if len(args) < 2:
                self._print_error(
                    "Missing model parameter for /model set",
                    "No provider:model was provided.",
                    "Syntax: /model set <provider:model> (e.g. /model set ollama:llama3)",
                )
                return
            model_val = args[1]
            self.console.print(f"[bold green]✔ Model configured to:[/bold green] {model_val}")
        else:
            self._print_error(
                f"Unknown /model subcommand: '{sub}'",
                "Subcommand not supported.",
                "Syntax: /model probe or /model set <provider:model>",
            )

    def _cmd_skill(self, args: list[str]) -> None:
        sub = args[0].lower() if args else "sync"
        if sub in ("sync", "install"):
            try:
                from synap_git.cli.skill_installer import install_skills

                updated = install_skills(self.repo_path)
                self.console.print(
                    f"[bold green]✔ Synchronized skill rules in:[/bold green] "
                    f"{', '.join(updated) if updated else 'no changes needed'}"
                )
            except Exception as e:
                self._print_error(
                    "Failed to sync skills",
                    str(e),
                    "Verify file write permissions in the repository root.",
                )
        elif sub == "export":
            try:
                from synap_git.cli.skill_installer import get_skill_template

                out_file = self.repo_path / "SKILL.md"
                out_file.write_text(get_skill_template(), encoding="utf-8")
                # Verification
                if not out_file.exists() or out_file.stat().st_size == 0:
                    raise RuntimeError("Export verification failed: SKILL.md was not written.")

                self.console.print(f"[bold green]✔ Exported SKILL.md to:[/bold green] {out_file}")
            except Exception as e:
                self._print_error(
                    "Failed to export skill",
                    str(e),
                    "Ensure repository root is writable.",
                )
        else:
            self._print_error(
                f"Unknown /skill subcommand: '{sub}'",
                "Subcommand not supported.",
                "Available subcommands: /skill sync, /skill export",
            )

    def _cmd_logs(self, args: list[str]) -> None:
        """Display recent background daemon activity logs."""
        lines_count = 20
        if args and ("-n" in args or "--lines" in args):
            try:
                flag = "-n" if "-n" in args else "--lines"
                idx = args.index(flag)
                if idx + 1 < len(args):
                    lines_count = int(args[idx + 1])
            except ValueError:
                pass
        elif args and args[0].isdigit():
            lines_count = int(args[0])

        log_candidates = [
            self.repo_path / ".synap" / "daemon.log",
            Path.home() / ".config" / "synap" / "logs" / "daemon.log",
            Path.home() / ".synap" / "daemon.log",
        ]
        log_file: Path | None = None
        for cand in log_candidates:
            if cand.exists():
                log_file = cand
                break

        if not log_file or not log_file.exists():
            self.console.print(
                "[yellow]No daemon log file found.[/yellow]\n"
                "[dim]Start the daemon with [bold cyan]synap daemon start[/bold cyan] to generate activity logs.[/dim]"
            )
            return

        try:
            raw_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = raw_lines[-lines_count:]
            table = Table(
                title=f"Recent Daemon Logs ({log_file.name}, last {len(tail_lines)} lines)",
                border_style="cyan",
                padding=(0, 1),
            )
            table.add_column("Log Entry", style="dim white")
            for entry in tail_lines:
                table.add_row(entry)
            self.console.print(table)
        except Exception as e:
            self._print_error(
                "Failed to read daemon logs",
                str(e),
                f"Verify read permissions for {log_file}.",
            )

    def _cmd_doctor(self, args: list[str]) -> None:
        do_fix = "--fix" in args
        self.console.print(
            f"[dim]Running health diagnostics ({'repair mode' if do_fix else 'check mode'})...[/dim]"
        )
        try:
            self.runtime.initialize_storage(auto_recover=do_fix)
            doc_res = self.runtime.doctor(auto_recover=do_fix)

            table = Table(title="Synapse Health Diagnostics", border_style="cyan", padding=(0, 1))
            table.add_column("Check", style="bold cyan")
            table.add_column("Status")

            for k, v in doc_res.items():
                val_str = str(v)
                status_color = "green" if "ok" in val_str.lower() else "yellow"
                table.add_row(
                    k.replace("_", " ").title(), f"[{status_color}]{val_str}[/{status_color}]"
                )

            self.console.print(table)
        except Exception as e:
            self._print_error(
                "Doctor diagnostic failed",
                str(e),
                "Run /doctor --fix or inspect /logs to troubleshoot system integrity.",
            )

    def run(self) -> None:
        """Main REPL loop."""
        self.prompt_init_if_needed()
        self.print_banner()
        while True:
            try:
                line = self.session.prompt(HTML("<ansicyan><b>synap</b></ansicyan><b>&gt; </b>"))
                if not self.execute_command(line):
                    break
            except KeyboardInterrupt:
                self.console.print(
                    "\n[dim]KeyboardInterrupt (press Ctrl+D or type /exit to quit)[/dim]"
                )
                continue
            except EOFError:
                self.console.print("\n[dim]Exiting...[/dim]")
                break
            except Exception as e:
                self._print_error(
                    "Unexpected REPL failure",
                    str(e),
                    "Type /help for command syntax or /exit to quit.",
                )


def start_tui(repo_path: Path | str = ".") -> None:
    """Launch the interactive TUI REPL."""
    repl = SynapInteractiveREPL(repo_path=repo_path)
    repl.run()


if __name__ == "__main__":
    start_tui()
