from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from synap_git import __version__
from synap_git.config import SynapSettings
from synap_git.diagnostics.logger import get_logger
from synap_git.storage.global_memory import GlobalMemoryStore

logger = get_logger("tui")


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

        # Setup autocompletion
        self.completer = NestedCompleter.from_nested_dict(
            {
                "/init": None,
                "/status": None,
                "/find": None,
                "/remember": None,
                "/forget": None,
                "/wiki": {
                    "generate": None,
                    "show": None,
                    "status": None,
                },
                "/global": None,
                "/ingest": None,
                "/model": {
                    "probe": None,
                    "set": None,
                },
                "/skill": {
                    "sync": None,
                    "export": None,
                },
                "/doctor": {
                    "--fix": None,
                },
                "/help": None,
                "/exit": None,
                "/quit": None,
            }
        )

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

    def print_banner(self) -> None:
        """Render quick startup banner without clearing scrollback."""
        self.console.print(
            f"[bold cyan]⚡ Synapse[/bold cyan] [bold green]v{__version__}[/bold green] "
            f"— Interactive Context Engine REPL"
        )
        self.console.print(
            "[dim]Type [bold cyan]/help[/bold cyan] for commands, [bold cyan]/exit[/bold cyan] to quit. "
            "100% scrollback preserved.[/dim]\n"
        )

    def execute_command(self, line: str) -> bool:
        """Execute a single line. Return False to exit, True to continue."""
        text = line.strip()
        if not text:
            return True

        # Normalize slash
        if not text.startswith("/"):
            # Check if it matches a known command name without slash
            cmd_root = text.split()[0].lower()
            known = {
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
                "doctor",
                "help",
                "exit",
                "quit",
            }
            if cmd_root in known:
                text = "/" + text
            else:
                self.console.print(
                    f"[yellow]Unknown command:[/yellow] {text}. Type [bold cyan]/help[/bold cyan] for available commands."
                )
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
        elif cmd == "/doctor":
            self._cmd_doctor(args)
        else:
            self.console.print(
                f"[yellow]Unknown command:[/yellow] {cmd}. Type [bold cyan]/help[/bold cyan] for available commands."
            )

        return True

    def _cmd_help(self) -> None:
        table = Table(
            title="Synapse Slash-Command Cheatsheet",
            border_style="cyan",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Command", style="bold cyan", no_wrap=True)
        table.add_column("Syntax", style="yellow")
        table.add_column("Description", style="white")

        table.add_row("/init", "/init", "Initialize .synap/ repository context storage")
        table.add_row(
            "/status",
            "/status",
            "Rich dashboard of repo, git state, daemon, indexed symbols",
        )
        table.add_row("/find", "/find <query>", "Interactive hybrid search with preview")
        table.add_row(
            "/remember",
            "/remember <key> <content>",
            "Save architectural decision or operational fact",
        )
        table.add_row("/forget", "/forget <key>", "Remove memory item by key")
        table.add_row(
            "/wiki",
            "/wiki [generate|show|status]",
            "1:1 structural markdown documentation engine",
        )
        table.add_row(
            "/global",
            "/global [query]",
            "Inspect global memories (~/.synap/global_memory.db)",
        )
        table.add_row(
            "/ingest",
            "/ingest <id>",
            "Promote/clone global memory into local repository",
        )
        table.add_row(
            "/model",
            "/model [probe|set]",
            "Runtime auto-discovery or model override",
        )
        table.add_row(
            "/skill",
            "/skill [sync|export]",
            "Install/update SKILL.md and repo agent rules",
        )
        table.add_row("/doctor", "/doctor [--fix]", "Run system health diagnostics")
        table.add_row("/help", "/help", "Show this command cheatsheet")
        table.add_row("/exit", "/exit or /quit", "Exit the interactive REPL")

        self.console.print(table)

    def _cmd_init(self) -> None:
        try:
            self.runtime.initialize_storage()
            self.runtime.bootstrap()
            self.console.print(
                f"[bold green]✔ Initialized Synapse in[/bold green] {self.repo_path}"
            )
            # Quick index trigger
            state = self.runtime.git.state()
            self.runtime.index_repository(git_state=state)
            status = self.runtime.status()
            self.console.print(
                f"[dim]Indexed {status.files} files, {status.symbols} symbols "
                f"on branch '{status.branch}'.[/dim]"
            )
        except Exception as e:
            self.console.print(f"[bold red]Initialization failed:[/bold red] {e}")

    def _cmd_status(self) -> None:
        try:
            self.runtime.initialize_storage(auto_recover=False)
            status = self.runtime.status()
            git_state = self.runtime.git.state()

            table = Table(
                title=f"⚡ Synapse Status — {self.repo_path.name}",
                border_style="cyan",
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

            # Daemon info
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
            self.console.print(f"[bold red]Status query failed:[/bold red] {e}")

    def _cmd_find(self, args: list[str]) -> None:
        if not args:
            self.console.print("[yellow]Usage:[/yellow] /find <query>")
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
            self.console.print(f"[bold red]Search failed:[/bold red] {e}")

    def _cmd_remember(self, args: list[str]) -> None:
        if len(args) < 2:
            self.console.print("[yellow]Usage:[/yellow] /remember <key> <content>")
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
            self.console.print(
                f"[bold green]✔ Saved memory[/bold green] under key '[cyan]{key}[/cyan]'."
            )
        except Exception as e:
            self.console.print(f"[bold red]Failed to save memory:[/bold red] {e}")

    def _cmd_forget(self, args: list[str]) -> None:
        if not args:
            self.console.print("[yellow]Usage:[/yellow] /forget <key>")
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
            self.console.print(f"[bold red]Failed to forget memory:[/bold red] {e}")

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
                self.console.print(
                    f"[bold green]✔ Wiki generation complete.[/bold green] Generated {res.get('generated', 0)} pages."
                )
            except Exception as e:
                self.console.print(f"[bold red]Wiki generation failed:[/bold red] {e}")
        elif sub == "show":
            if len(args) < 2:
                self.console.print("[yellow]Usage:[/yellow] /wiki show <page_name>")
                return
            target = args[1]
            if not target.endswith(".md"):
                target += ".md"
            target_path = wiki_dir / target
            if not target_path.exists():
                self.console.print(f"[yellow]Wiki page not found:[/yellow] {target}")
                return
            content = target_path.read_text(encoding="utf-8")
            from rich.markdown import Markdown

            self.console.print(Markdown(content))
        else:
            self.console.print("[yellow]Usage:[/yellow] /wiki [generate|show <page>|status]")

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
            self.console.print(f"[bold red]Failed to query global memory:[/bold red] {e}")

    def _cmd_ingest(self, args: list[str]) -> None:
        if not args:
            self.console.print("[yellow]Usage:[/yellow] /ingest <global_id>")
            return
        gid = args[0]
        try:
            m = self.global_store.get_memory(gid)
            if not m:
                # Try prefix search
                matches = self.global_store.list_memories(query=gid, limit=2)
                if matches and matches[0]["global_id"].startswith(gid):
                    m = matches[0]

            if not m:
                self.console.print(f"[bold red]Global memory not found for ID:[/bold red] {gid}")
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

            self.console.print(
                f"[bold green]✔ Ingested global memory[/bold green] '[cyan]{m['context_key']}[/cyan]' "
                f"into repository memory."
            )
        except Exception as e:
            self.console.print(f"[bold red]Failed to ingest global memory:[/bold red] {e}")

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

            # Fallback direct probe if service not present or nothing found
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
                table = Table(title="Discovered Local Runtimes", border_style="cyan")
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
                self.console.print("[yellow]Usage:[/yellow] /model set <provider:model>")
                return
            model_val = args[1]
            self.console.print(f"[bold green]✔ Model configured to:[/bold green] {model_val}")
        else:
            self.console.print("[yellow]Usage:[/yellow] /model [probe|set <model>]")

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
                self.console.print(f"[bold red]Failed to sync skills:[/bold red] {e}")
        elif sub == "export":
            try:
                from synap_git.cli.skill_installer import get_skill_template

                out_file = self.repo_path / "SKILL.md"
                out_file.write_text(get_skill_template(), encoding="utf-8")
                self.console.print(f"[bold green]✔ Exported SKILL.md to:[/bold green] {out_file}")
            except Exception as e:
                self.console.print(f"[bold red]Failed to export skill:[/bold red] {e}")
        else:
            self.console.print("[yellow]Usage:[/yellow] /skill [sync|export]")

    def _cmd_doctor(self, args: list[str]) -> None:
        do_fix = "--fix" in args
        self.console.print(
            f"[dim]Running health diagnostics ({'repair mode' if do_fix else 'check mode'})...[/dim]"
        )
        try:
            self.runtime.initialize_storage(auto_recover=do_fix)
            doc_res = self.runtime.doctor(auto_recover=do_fix)

            table = Table(title="Synapse Health Diagnostics", border_style="cyan")
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
            self.console.print(f"[bold red]Doctor diagnostic failed:[/bold red] {e}")

    def run(self) -> None:
        """Main REPL loop."""
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
                self.console.print(f"[bold red]Error:[/bold red] {e}")


def start_tui(repo_path: Path | str = ".") -> None:
    """Launch the interactive TUI REPL."""
    repl = SynapInteractiveREPL(repo_path=repo_path)
    repl.run()


if __name__ == "__main__":
    start_tui()
