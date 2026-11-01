from __future__ import annotations

import functools
import inspect
import json
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from synap_git.indexer.engine import SynapRuntime
from synap_git.security.redactor import SecretRedactor
from synap_git.security.sanitizer import IngestionSanitizer


class AmbiguousSymbolError(ValueError):
    """Raised when a symbol name matches multiple files in the repository."""

    def __init__(self, symbol: str, candidates: list[str]) -> None:
        self.symbol = symbol
        self.candidates = candidates
        cand_str = ", ".join(candidates)
        super().__init__(
            f"Symbol '{symbol}' is ambiguous and matches multiple files: {cand_str}. "
            f"Please specify 'file_path' to disambiguate."
        )


def get_synap_mcp_config(ide: str = "generic") -> dict[str, Any]:
    """Retrieve the exact JSON configuration block needed to connect coding agents to Synap."""
    import shutil

    synap_bin = shutil.which("synap") or "synap"
    server_cmd = "synap" if shutil.which("synap") else synap_bin
    server_args = ["mcp", "serve"]

    config = {
        "command": server_cmd,
        "args": server_args,
    }
    return {
        "command": server_cmd,
        "args": server_args,
        "mcpServers": {
            "synap": config,
        },
    }


class SynapMCPFacade:
    """Model Context Protocol facade over the simplified Synap runtime."""

    def __init__(self, runtime: SynapRuntime) -> None:
        self.runtime = runtime

    def get_status(self) -> dict[str, Any]:
        status = self.runtime.status()
        return status.__dict__

    def get_mcp_config(self, ide: str = "generic", export_path: str = "") -> dict[str, Any]:
        """Retrieve or export the exact JSON configuration block needed to connect coding agents."""
        cfg = get_synap_mcp_config(ide=ide)
        server_cmd = cfg["command"]
        server_args = cfg["args"]
        ide_clean = ide.lower().strip()

        ide_paths: dict[str, list[str]] = {
            "cursor": [
                ".cursor/mcp.json (project-specific)",
                "~/.cursor/mcp.json (global)",
            ],
            "windsurf": [
                "~/.codeium/windsurf/mcp_config.json",
                "~/.config/Codeium/windsurf/mcp_config.json",
            ],
            "claude": [
                "Run CLI: claude mcp add synap -- synap mcp serve",
                "~/.claude.json",
            ],
            "cline": [
                "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            ],
            "aider": [
                "Run with: aider --mcp-server synap",
            ],
        }

        exported = False
        saved_to: str | None = None
        if export_path.strip():
            target_p = Path(export_path.strip())
            if not target_p.is_absolute():
                target_p = self.runtime.settings.repository_path / target_p
            target_p.parent.mkdir(parents=True, exist_ok=True)
            target_p.write_text(
                json.dumps({"mcpServers": cfg["mcpServers"]}, indent=2) + "\n",
                encoding="utf-8",
            )
            exported = True
            saved_to = str(target_p)

        locations = ide_paths.get(ide_clean) or ide_paths.get("cursor") or []

        return {
            "command": server_cmd,
            "args": server_args,
            "config": {"command": server_cmd, "args": server_args},
            "mcpServers": cfg["mcpServers"],
            "json_snippet": json.dumps({"mcpServers": cfg["mcpServers"]}, indent=2),
            "ide": ide_clean,
            "config_locations": locations,
            "exported": exported,
            "saved_to": saved_to,
        }

    def get_session_preamble(self) -> dict[str, Any]:
        git_state = self.runtime.git.state()
        branch = git_state.effective_branch
        head_commit = git_state.head_commit

        # Check if index is already up to date with HEAD or store has indexed files
        last_indexed: str | None = None
        if self.runtime.store.path.exists():
            try:
                last_indexed = self.runtime.store.get_last_indexed_commit()
            except Exception:
                pass

        already_indexed = last_indexed is not None and last_indexed == head_commit
        is_clean_indexed = not git_state.is_dirty and last_indexed is not None

        # Do not run full synchronous re-indexing if repository is clean or already indexed
        if not already_indexed and not is_clean_indexed and head_commit:
            try:
                self.runtime.index_repository(git_state=git_state)
            except Exception:
                pass

        latest_cp = self.runtime.store.get_latest_checkpoint(branch)
        approved_lessons = self.runtime.store.get_lessons("approved")
        recent_decisions = self.runtime.store.get_decisions(branch=branch, limit=3)
        recent_activity = self.runtime.store.get_activity(branch=branch, limit=5)

        parsed_cp = None
        if latest_cp:
            parsed_cp = dict(latest_cp)
            if "changed_files" in parsed_cp and isinstance(parsed_cp["changed_files"], str):
                try:
                    parsed_cp["changed_files"] = json.loads(parsed_cp["changed_files"])
                except Exception:
                    pass

        # Query counts directly to avoid redundant git status calls and overhead
        files_count = 0
        symbols_count = 0
        try:
            with self.runtime.store.connect() as conn:
                row = conn.execute(
                    "SELECT (SELECT COUNT(*) FROM files), (SELECT COUNT(*) FROM symbols)"
                ).fetchone()
                if row:
                    files_count, symbols_count = int(row[0] or 0), int(row[1] or 0)
        except Exception:
            pass

        recent_memories = self.runtime.store.get_recent_memory(limit=3)

        diff_ranges = self.runtime.git.get_dirty_diff_ranges() if git_state.is_dirty else {}
        blast_radius = self.runtime.store.get_blast_radius(diff_ranges)
        active_files = list(git_state.dirty_files) if git_state.is_dirty else None
        hubs = self.runtime.store.compute_pagerank(active_files=active_files, limit=5)

        # Build compact high-density markdown preamble
        dirty_desc = (
            f"DIRTY ({len(git_state.dirty_files)} files)" if git_state.is_dirty else "CLEAN"
        )
        p_lines = [
            "# SYNAPSE STRUCTURAL PREAMBLE",
            f"- Branch: `{branch}` | Commit: `{(head_commit or 'none')[:8]}` | Status: {dirty_desc} | Index: {files_count} files, {symbols_count} symbols",
            "",
        ]
        if parsed_cp:
            p_lines.append("## Active Checkpoint")
            p_lines.append(f"- Doing: {parsed_cp.get('doing', 'N/A')}")
            p_lines.append(f"- Next Step: {parsed_cp.get('next_step', 'N/A')}")
            if parsed_cp.get("blockers") and parsed_cp.get("blockers") != "none":
                p_lines.append(f"- Blockers: {parsed_cp.get('blockers')}")
            p_lines.append("")

        if blast_radius.get("touched_symbols"):
            p_lines.append("## Git Blast Radius (Impacted Callers)")
            for sym in blast_radius["touched_symbols"][:4]:
                name = sym["name"]
                path = sym["path"]
                line = sym.get("start_line", 1)
                direct = [
                    f"`{c['name']}` ({c['path']}:{c['start_line']})"
                    for c in blast_radius.get("direct_callers", [])
                    if c.get("impacts") == name
                ][:2]
                impacted_tests = [
                    f"`{t['name']}` ({t['path']})"
                    for t in blast_radius.get("impacted_tests", [])
                    if t.get("impacts") == name
                ][:2]
                callers_str = ", ".join(direct) if direct else "No internal callers"
                tests_str = f" | Tests: {', '.join(impacted_tests)}" if impacted_tests else ""
                p_lines.append(
                    f"- Touched `{name}` ({path}:{line}) -> Callers: {callers_str}{tests_str}"
                )
            p_lines.append("")

        if hubs:
            p_lines.append("## Architectural Hubs (PageRank)")
            for h in hubs[:5]:
                p_lines.append(f"- `{h['name']}` ({h['path']}) [{h['score']}]")
            p_lines.append("")

        if approved_lessons:
            p_lines.append("## Negative Constraints (Strict Rules)")
            for idx, lesson in enumerate(approved_lessons[:3], 1):
                p_lines.append(
                    f"- [RULE-{idx:02d}] DO NOT: {lesson.get('what_failed', '')} - {lesson.get('why_failed', '')}"
                )
            p_lines.append("")

        if recent_memories:
            p_lines.append("## Working Memory")
            for m in recent_memories[:3]:
                txt = m.get("summary") or m.get("payload", "")
                p_lines.append(f"- **{m.get('context_key', 'note')}**: {txt}")
            p_lines.append("")

        compact_preamble = "\n".join(p_lines).strip()

        return {
            "branch": branch,
            "git_commit": head_commit,
            "is_dirty": git_state.is_dirty,
            "dirty_files": list(git_state.dirty_files),
            "stats": {"indexed_files": files_count, "indexed_symbols": symbols_count},
            "latest_checkpoint": parsed_cp,
            "blast_radius": blast_radius,
            "architectural_hubs": hubs,
            "approved_lessons": approved_lessons,
            "recent_decisions": recent_decisions,
            "recent_memories": recent_memories,
            "recent_activity": recent_activity,
            "compact_preamble": compact_preamble,
        }

    def search(
        self,
        query: str,
        max_tokens: int = 4000,
        synthesize_answer: bool = False,
        summary_only: bool = False,
    ) -> dict[str, Any]:
        sig = inspect.signature(self.runtime.query_hybrid)
        if "synthesize_answer" in sig.parameters:
            result, ctx, debug = self.runtime.query_hybrid(
                query,
                max_tokens=max_tokens,
                synthesize_answer=False if summary_only else synthesize_answer,
            )
        else:
            result, ctx, debug = self.runtime.query_hybrid(query, max_tokens=max_tokens)

        if summary_only:
            summaries: list[dict[str, Any]] = []
            if isinstance(ctx, list):
                for item in ctx:
                    if isinstance(item, dict):
                        summaries.append(
                            {
                                "symbol": item.get("name", ""),
                                "kind": item.get("kind", ""),
                                "path": item.get("source_path", ""),
                                "lines": f"{item.get('start_line', 1)}-{item.get('end_line', 1)}",
                                "reason": item.get("reason", ""),
                            }
                        )
            return {
                "matches": summaries,
                "total_matches": len(summaries),
                "query": query,
            }

        return {"result": result, "context": ctx, "trace": debug}

    def create_checkpoint(
        self,
        doing: str,
        changed_files: list[str] | None = None,
        next_step: str = "",
        blockers: str = "none",
    ) -> dict[str, Any]:
        if not doing.strip():
            raise ValueError("The 'doing' field cannot be empty.")
        if not changed_files:
            git_state = self.runtime.git.state()
            changed_files = list(git_state.dirty_files) if git_state.is_dirty else ["none"]
        if not blockers:
            blockers = "none"

        doing, changed_files, next_step, blockers = IngestionSanitizer.sanitize_checkpoint(
            doing, changed_files, next_step, blockers
        )
        doing = SecretRedactor.redact(doing)
        changed_files = [SecretRedactor.redact(f) for f in changed_files]
        next_step = SecretRedactor.redact(next_step)
        blockers = SecretRedactor.redact(blockers)

        status = self.runtime.status()
        checkpoint_id = str(uuid.uuid4())
        branch = status.branch
        commit = status.git_commit or "unknown"
        self.runtime.store.put_checkpoint(
            checkpoint_id, branch, commit, doing, json.dumps(changed_files), next_step, blockers
        )
        try:
            self.runtime.store.put_activity(
                activity_id=str(uuid.uuid4()),
                branch=branch,
                commit_hash=commit,
                action=f"checkpoint: {doing}",
                files=json.dumps(changed_files),
            )
        except Exception:
            pass
        return {"status": "success", "checkpoint_id": checkpoint_id}

    def restore_checkpoint(self, checkpoint_id: str = "latest") -> dict[str, Any]:
        if checkpoint_id and checkpoint_id.lower() != "latest":
            cp = self.runtime.store.get_checkpoint(checkpoint_id)
            if not cp:
                raise ValueError(f"No checkpoint found with ID '{checkpoint_id}'.")
            return dict(cp)

        status = self.runtime.status()
        cp = self.runtime.store.get_latest_checkpoint(status.branch)
        if not cp:
            raise ValueError(f"No checkpoints found for branch '{status.branch}'.")
        return dict(cp)

    def list_checkpoints(self, limit: int = 5) -> dict[str, Any]:
        status = self.runtime.status()
        cps = self.runtime.store.get_checkpoints(status.branch)
        return {
            "branch": status.branch,
            "count": len(cps[:limit]),
            "checkpoints": [dict(cp) for cp in cps[:limit]],
        }

    def log_decision(self, content: str, context_info: str = "") -> dict[str, Any]:
        if not content.strip():
            raise ValueError("The 'content' field cannot be empty.")
        content = IngestionSanitizer.sanitize_note(content)
        context_info = IngestionSanitizer.sanitize_note(context_info) if context_info else ""
        content = SecretRedactor.redact(content)
        context_info = SecretRedactor.redact(context_info) if context_info else ""

        status = self.runtime.status()
        decision_id = str(uuid.uuid4())
        branch = status.branch
        commit = status.git_commit or "unknown"
        self.runtime.store.put_decision(decision_id, branch, commit, content, context_info)
        try:
            self.runtime.store.put_activity(
                activity_id=str(uuid.uuid4()),
                branch=branch,
                commit_hash=commit,
                action=f"decision: {content}",
            )
        except Exception:
            pass
        return {"status": "success", "decision_id": decision_id}

    def verify_system(self) -> dict[str, Any]:
        res = self.runtime.doctor()
        return res

    def submit_lesson_analysis(self, lesson_id: str, why_failed: str) -> dict[str, Any]:
        why_failed = IngestionSanitizer.sanitize_note(why_failed)
        why_failed = SecretRedactor.redact(why_failed)

        self.runtime.store.update_lesson(lesson_id, why_failed, "pending", actor="mcp_agent")
        try:
            status = self.runtime.status()
            self.runtime.store.put_activity(
                activity_id=str(uuid.uuid4()),
                branch=status.branch,
                commit_hash=status.git_commit or "unknown",
                action=f"lesson_analysis: {lesson_id}",
            )
        except Exception:
            pass
        return {"status": "success", "message": "Lesson awaiting human approval"}

    def get_outline(self, file_path: str) -> dict[str, Any]:
        if not file_path.strip():
            raise ValueError("The 'file_path' parameter cannot be empty.")
        clean_path = file_path.strip().lstrip("/")
        file_record = self.runtime.store.get_file_by_path(clean_path)
        if not file_record:
            with self.runtime.store.connect() as conn:
                rows = conn.execute(
                    "SELECT path, file_id, language FROM files WHERE path LIKE ?",
                    (f"%{clean_path}",),
                ).fetchall()
                if rows:
                    file_record = dict(rows[0])

        if not file_record:
            raise ValueError(f"File '{file_path}' not found in index.")

        symbols = self.runtime.store.get_symbols_by_file(file_record["file_id"])
        return {
            "path": file_record["path"],
            "language": file_record.get("language", "unknown"),
            "symbol_count": len(symbols),
            "symbols": [
                {
                    "name": s["name"],
                    "kind": s["kind"],
                    "lines": f"{s['start_line']}-{s['end_line']}",
                    "id": s["symbol_id"],
                }
                for s in symbols
            ],
        }

    def get_neighborhood(
        self,
        symbol: str,
        file_path: str | None = None,
        direction: str = "both",
        depth: int = 2,
    ) -> dict[str, Any]:
        clean_sym = symbol.strip()
        if not clean_sym:
            raise ValueError("The 'symbol' parameter cannot be empty.")
        resolved_id = clean_sym
        with self.runtime.store.connect() as conn:
            if file_path:
                norm = file_path.strip().lstrip("/")
                rows = conn.execute(
                    """SELECT s.symbol_id, f.path FROM symbols s
                       JOIN files f ON s.file_id = f.file_id
                       WHERE (s.symbol_id = ? OR s.name = ?) AND (f.path = ? OR f.path LIKE ?)
                       LIMIT 10""",
                    (clean_sym, clean_sym, norm, f"%{norm}"),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT s.symbol_id, f.path FROM symbols s
                       JOIN files f ON s.file_id = f.file_id
                       WHERE s.symbol_id = ? OR s.name = ?
                       LIMIT 10""",
                    (clean_sym, clean_sym),
                ).fetchall()

            if rows:
                matching_paths = list(dict.fromkeys(str(r[1]) for r in rows))
                if len(matching_paths) > 1 and not file_path:
                    exact_id = [r[0] for r in rows if str(r[0]) == clean_sym]
                    if len(exact_id) == 1:
                        resolved_id = str(exact_id[0])
                    else:
                        raise AmbiguousSymbolError(clean_sym, matching_paths)
                elif len(matching_paths) > 1 and file_path:
                    norm = file_path.strip().lstrip("/")
                    exact_matches = [r[0] for r in rows if str(r[1]) == norm]
                    if len(exact_matches) == 1:
                        resolved_id = str(exact_matches[0])
                    else:
                        raise AmbiguousSymbolError(clean_sym, matching_paths)
                else:
                    resolved_id = str(rows[0][0])

        dir_clean = direction.lower().strip()
        if dir_clean in ("upstream", "callers", "incoming", "parents"):
            actual_dir = "upstream"
        elif dir_clean in ("downstream", "callees", "outgoing", "dependencies", "children"):
            actual_dir = "downstream"
        else:
            actual_dir = "both"

        neighbors = self.runtime.store.get_neighborhood(
            resolved_id, depth=depth, direction=actual_dir
        )
        return {
            "symbol": symbol,
            "file_path": file_path,
            "resolved_id": resolved_id,
            "direction": actual_dir,
            "depth": depth,
            "neighbors_count": len(neighbors),
            "neighbors": [
                {
                    "name": n["name"],
                    "kind": n["kind"],
                    "path": n.get("source_path", ""),
                    "distance": n.get("distance", 0),
                    "lines": f"{n.get('start_line', 1)}-{n.get('end_line', 1)}",
                }
                for n in neighbors
            ],
        }

    def read_symbol(self, symbol: str, file_path: str | None = None) -> dict[str, Any]:
        clean_sym = symbol.strip()
        if not clean_sym:
            raise ValueError("The 'symbol' parameter cannot be empty.")
        with self.runtime.store.connect() as conn:
            if file_path:
                norm = file_path.strip().lstrip("/")
                rows = conn.execute(
                    """SELECT s.name, s.kind, s.start_line, s.end_line, f.path
                       FROM symbols s JOIN files f ON s.file_id = f.file_id
                       WHERE (s.symbol_id = ? OR s.name = ?) AND (f.path = ? OR f.path LIKE ?)
                       LIMIT 10""",
                    (clean_sym, clean_sym, norm, f"%{norm}"),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT s.name, s.kind, s.start_line, s.end_line, f.path
                       FROM symbols s JOIN files f ON s.file_id = f.file_id
                       WHERE s.symbol_id = ? OR s.name = ?
                       LIMIT 10""",
                    (clean_sym, clean_sym),
                ).fetchall()

        if not rows:
            raise ValueError(f"Symbol '{symbol}' not found.")

        matching_paths = list(dict.fromkeys(str(r[4]) for r in rows))
        if len(matching_paths) > 1:
            if file_path:
                norm = file_path.strip().lstrip("/")
                exact_matches = [r for r in rows if str(r[4]) == norm]
                if len(exact_matches) == 1:
                    row = exact_matches[0]
                else:
                    raise AmbiguousSymbolError(clean_sym, matching_paths)
            else:
                raise AmbiguousSymbolError(clean_sym, matching_paths)
        else:
            row = rows[0]

        name, kind, start_line, end_line, path = (
            str(row[0]),
            str(row[1]),
            int(row[2]),
            int(row[3]),
            str(row[4]),
        )
        full_path = self.runtime.settings.repository_path / path
        if not full_path.exists():
            raise ValueError(f"File '{path}' for symbol '{symbol}' does not exist on disk.")

        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        slice_lines = lines[max(0, start_line - 1) : end_line]
        numbered = [f"{start_line + i:4d} | {line}" for i, line in enumerate(slice_lines)]
        return {
            "name": name,
            "kind": kind,
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
            "lines_count": len(slice_lines),
            "code": "\n".join(slice_lines),
            "numbered_code": "\n".join(numbered),
        }

    def get_diff(self, file_path: str = "", staged: bool = False) -> dict[str, Any]:
        import shutil
        import subprocess

        git_bin = shutil.which("git") or "git"
        cmd = [git_bin, "diff"]
        if staged:
            cmd.append("--staged")
        cmd.extend(["-U3", "--"])
        if file_path:
            cmd.append(file_path.strip().lstrip("/"))
        res = subprocess.run(
            cmd,
            cwd=self.runtime.settings.repository_path,
            capture_output=True,
            text=True,
        )
        return {"diff": res.stdout, "staged": staged, "file": file_path or "all"}

    def get_test_recommendations(self, file_path: str = "") -> dict[str, Any]:
        target_file = file_path.strip().lstrip("/")
        recommended_tests: list[str] = []

        # 1. AST blast radius tests
        blast = self.get_blast_radius()
        for t in blast.get("impacted_tests", []):
            p = t.get("path")
            if p and p not in recommended_tests:
                recommended_tests.append(p)

        # 2. Convention-based mapping
        stems_to_check: list[str] = []
        if target_file:
            stems_to_check.append(Path(target_file).stem)
        else:
            git_state = self.runtime.git.state()
            for df in git_state.dirty_files:
                stems_to_check.append(Path(df).stem)

        with self.runtime.store.connect() as conn:
            for stem in stems_to_check:
                rows = conn.execute(
                    "SELECT path FROM files WHERE path LIKE ? OR path LIKE ?",
                    (f"%test_{stem}.py", f"%{stem}_test.py"),
                ).fetchall()
                for r in rows:
                    p = str(r[0])
                    if p not in recommended_tests:
                        recommended_tests.append(p)

        unique_tests = sorted(set(recommended_tests))
        cmd = f".venv/bin/pytest {' '.join(unique_tests)}" if unique_tests else ".venv/bin/pytest"
        return {"test_files": unique_tests, "recommended_command": cmd}

    def get_approved_memory(self) -> dict[str, Any]:
        lessons = self.runtime.store.get_lessons("approved")
        return {"status": "success", "lessons": lessons}

    def get_pending_memory(self) -> dict[str, Any]:
        lessons = self.runtime.store.get_lessons("pending")
        return {"status": "success", "lessons": lessons}

    def signal_low_context(self, token_count: int, capacity: int) -> dict[str, Any]:
        percentage = token_count / capacity if capacity > 0 else 0
        threshold = self.runtime.settings.checkpoint_threshold
        should_checkpoint = percentage >= threshold

        message = f"Context usage is at {percentage:.1%}. "
        if should_checkpoint:
            message += f"Threshold ({threshold:.1%}) reached. Checkpoint recommended."
            # Emit CLI notification
            import sys

            sys.stderr.write(
                f"\n[Synapse] ⚠ Agent at {percentage:.0%} context — checkpoint recommended.\n"
            )
        else:
            message += f"Context is within limits (threshold {threshold:.1%})."

        return {"should_checkpoint": should_checkpoint, "message": message}

    def remember(self, key: str, content: str, summary: str = "") -> dict[str, Any]:
        if not key.strip() or not content.strip():
            raise ValueError("Both 'key' and 'content' are required.")
        key = IngestionSanitizer.sanitize_note(key)
        content = IngestionSanitizer.sanitize_note(content)
        summary = IngestionSanitizer.sanitize_note(summary) if summary else ""
        key = SecretRedactor.redact(key)
        content = SecretRedactor.redact(content)
        summary = SecretRedactor.redact(summary) if summary else ""

        memory_id = str(uuid.uuid4())
        self.runtime.store.store_memory(
            memory_id=memory_id,
            context_key=key,
            payload=content,
            summary=summary,
        )
        try:
            status = self.runtime.status()
            self.runtime.store.put_activity(
                activity_id=str(uuid.uuid4()),
                branch=status.branch,
                commit_hash=status.git_commit or "unknown",
                action=f"remember: {key}",
            )
        except Exception:
            pass
        return {"status": "success", "memory_id": memory_id, "key": key}

    def recall(self, key: str = "", limit: int = 10) -> dict[str, Any]:
        memories = self.runtime.store.get_recent_memory(
            context_key=key.strip() if key.strip() else None,
            limit=limit,
        )
        return {"memories": memories, "count": len(memories)}

    def get_blast_radius(self) -> dict[str, Any]:
        git_state = self.runtime.git.state()
        diff_ranges = self.runtime.git.get_dirty_diff_ranges() if git_state.is_dirty else {}
        return self.runtime.store.get_blast_radius(diff_ranges)

    def get_skeleton(self, file_path: str) -> dict[str, Any]:
        clean_path = file_path.strip().lstrip("/")
        full_path = self.runtime.settings.repository_path / clean_path
        if not full_path.exists() or not full_path.is_file():
            raise ValueError(f"File not found: {clean_path}")
        skeleton_text = self.runtime.parser_registry.skeletonize(full_path)
        return {
            "path": clean_path,
            "skeleton": skeleton_text,
            "lines": len(skeleton_text.splitlines()),
        }


class SynapMCPServer:
    """Exposes Synap tools to AI agents via MCP Stdio."""

    def __init__(self, runtime: SynapRuntime) -> None:
        self.mcp = FastMCP("Synap Context Runtime")
        self.facade = SynapMCPFacade(runtime)
        self._register_tools()

    def _register_tools(self) -> None:
        from synap_git.diagnostics.logger import get_logger

        logger = get_logger("mcp_server")

        from collections.abc import Callable

        def _wrap(f: Callable[..., dict[str, Any]]) -> Callable[..., str]:
            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                trace_id = str(uuid.uuid4())
                dirty = False
                try:
                    git_state = self.facade.runtime.git.state()
                    dirty = git_state.is_dirty
                except Exception:
                    pass

                warnings = []
                if dirty:
                    warnings.append("Working tree is dirty. Index may be stale.")

                try:
                    start = time.monotonic()
                    data = f(*args, **kwargs)
                    duration_ms = (time.monotonic() - start) * 1000
                    logger.info(
                        "mcp_tool_invoked",
                        tool=f.__name__,
                        latency_ms=duration_ms,
                    )

                    try:
                        self.facade.runtime.trace_store.record_trace(
                            trace_type="mcp",
                            summary=f"MCP Tool Invoked: {f.__name__}",
                            details={
                                "tool": f.__name__,
                                "arguments": kwargs,
                                "duration_ms": duration_ms,
                                "success": True,
                                "trace_id": trace_id,
                                "dirty_tree": dirty,
                            },
                        )
                    except Exception as e:
                        import structlog

                        structlog.get_logger().error("suppressed_error_caught", error=str(e))

                    return json.dumps(
                        {
                            "ok": True,
                            "data": data,
                            "warnings": warnings,
                            "trace_id": trace_id,
                            "dirty_tree": dirty,
                        }
                    )
                except Exception as e:
                    msg = str(e)
                    code = "INTERNAL_ERROR"
                    suggestion = "Check daemon logs."
                    candidates: list[str] | None = None

                    if isinstance(e, AmbiguousSymbolError):
                        code = "AMBIGUOUS_SYMBOL"
                        candidates = e.candidates
                        suggestion = f"Specify 'file_path' with one of: {', '.join(e.candidates)}"
                    elif "ambiguous" in msg.lower():
                        code = "AMBIGUOUS_SYMBOL"
                        suggestion = (
                            "Provide the 'file_path' parameter to select the intended symbol."
                        )
                    elif "stale" in msg.lower():
                        code = "INDEX_STALE"
                        suggestion = "Run `synap reindex` or wait for daemon."
                    elif "no checkpoint" in msg.lower() or "not found" in msg.lower():
                        code = "NOT_FOUND"
                        suggestion = "Ensure the requested item exists in repository index."
                    elif "empty" in msg.lower() or "required" in msg.lower():
                        code = "INVALID_ARGUMENT"
                        suggestion = "Provide valid non-empty arguments for required parameters."

                    logger.error("mcp_tool_error", tool=f.__name__, error=msg, code=code)

                    try:
                        self.facade.runtime.trace_store.record_trace(
                            trace_type="mcp",
                            summary=f"MCP Tool Failed: {f.__name__}",
                            details={
                                "tool": f.__name__,
                                "arguments": kwargs,
                                "error": msg,
                                "code": code,
                                "success": False,
                                "trace_id": trace_id,
                            },
                        )
                    except Exception as trace_err:
                        import structlog

                        structlog.get_logger().error(
                            "suppressed_error_caught", error=str(trace_err)
                        )

                    error_info: dict[str, Any] = {
                        "code": code,
                        "message": msg,
                        "suggestion": suggestion,
                    }
                    if candidates is not None:
                        error_info["candidates"] = candidates

                    return json.dumps(
                        {
                            "ok": False,
                            "error": error_info,
                            "warnings": [],
                            "trace_id": trace_id,
                            "dirty_tree": dirty,
                        }
                    )

            wrapper.__signature__ = inspect.signature(f)  # type: ignore
            return wrapper

        @self.mcp.tool()
        @_wrap
        def get_status() -> dict[str, Any]:
            """Get current repository indexing status, active Git commit, branch, and indexed symbol/file counts."""
            return self.facade.get_status()

        @self.mcp.tool()
        @_wrap
        def get_session_preamble() -> dict[str, Any]:
            """Call this tool FIRST at session start or beginning of a task. Returns essential repository context: active branch, latest checkpoint, approved lessons (critical negative constraints), architectural hubs (PageRank), git blast radius, and working memory."""
            return self.facade.get_session_preamble()

        @self.mcp.tool()
        @_wrap
        def get_mcp_config(ide: str = "generic", export_path: str = "") -> dict[str, Any]:
            """Retrieve or export the exact JSON configuration block needed to connect coding agents (Cursor, Claude Code, Windsurf, Cline, Aider) to Synap.
            ide: Target IDE or tool format ('generic', 'cursor', 'windsurf', 'claude', 'cline', 'aider'). Default is 'generic'.
            export_path: Optional file path to export/write configuration JSON into."""
            return self.facade.get_mcp_config(ide=ide, export_path=export_path)

        @self.mcp.tool()
        @_wrap
        def search(
            query: str, max_tokens: int = 4000, summary_only: bool = False
        ) -> dict[str, Any]:
            """Search repository context. Set summary_only=True to return lightweight match summaries (progressive disclosure) instead of full context blocks.
            query: Natural language query, symbol name, or concept to search.
            max_tokens: Maximum token budget for returned context (default: 4000).
            summary_only: If True, returns concise symbol hits and line ranges (85% token savings)."""
            return self.facade.search(query, max_tokens, summary_only=summary_only)

        @self.mcp.tool()
        @_wrap
        def create_checkpoint(
            doing: str,
            changed_files: list[str] | None = None,
            next_step: str = "",
            blockers: str = "none",
        ) -> dict[str, Any]:
            """Save the current agent's thought process, working state, and intentions as a checkpoint.
            doing: Summary of currently active task or implementation focus.
            changed_files: Optional list of modified file paths. If omitted, dirty/uncommitted git files are auto-detected.
            next_step: Immediate next step or milestone to execute.
            blockers: Any blockers, failures, or constraints encountered (default: 'none')."""
            return self.facade.create_checkpoint(doing, changed_files, next_step, blockers)

        @self.mcp.tool()
        @_wrap
        def restore_checkpoint(checkpoint_id: str = "latest") -> dict[str, Any]:
            """Restore the latest checkpoint or a specific checkpoint by ID for the current branch to resume context.
            checkpoint_id: Checkpoint UUID, or 'latest' (default) to restore the most recent checkpoint."""
            return self.facade.restore_checkpoint(checkpoint_id)

        @self.mcp.tool()
        @_wrap
        def list_checkpoints(limit: int = 5) -> dict[str, Any]:
            """List recent checkpoints for the current branch to inspect prior work, progression, and decisions.
            limit: Maximum number of recent checkpoints to return (default: 5)."""
            return self.facade.list_checkpoints(limit=limit)

        @self.mcp.tool()
        @_wrap
        def log_decision(content: str, context_info: str = "") -> dict[str, Any]:
            """Log an architectural or technical decision to the project's persistent decision log.
            content: The decision made (e.g., 'Use SQLite WAL mode for concurrent queries').
            context_info: Optional background, trade-offs, or motivation for this decision."""
            return self.facade.log_decision(content, context_info)

        @self.mcp.tool()
        @_wrap
        def verify_system() -> dict[str, Any]:
            """Verify database integrity, Git repository state, and index consistency."""
            return self.facade.verify_system()

        @self.mcp.tool()
        @_wrap
        def submit_lesson_analysis(lesson_id: str, why_failed: str) -> dict[str, Any]:
            """Submit an analysis for a pending lesson (e.g., after a revert). Lesson remains pending until human approval.
            lesson_id: ID of the pending lesson to update.
            why_failed: Root-cause analysis explaining failure mechanics and prevention."""
            return self.facade.submit_lesson_analysis(lesson_id, why_failed)

        @self.mcp.tool()
        @_wrap
        def get_approved_memory() -> dict[str, Any]:
            """Retrieve APPROVED memory lessons and negative constraints that MUST be strictly adhered to."""
            return self.facade.get_approved_memory()

        @self.mcp.tool()
        @_wrap
        def get_pending_memory() -> dict[str, Any]:
            """Retrieve PENDING memory lessons currently awaiting human review."""
            return self.facade.get_pending_memory()

        @self.mcp.tool()
        @_wrap
        def signal_low_context(token_count: int, capacity: int) -> dict[str, Any]:
            """Signal that the agent is approaching context limits. Triggers a recommended checkpoint if over threshold.
            token_count: Current number of tokens consumed in conversation context.
            capacity: Total token capacity limit of the current model context window."""
            return self.facade.signal_low_context(token_count, capacity)

        @self.mcp.tool()
        @_wrap
        def get_outline(file_path: str) -> dict[str, Any]:
            """Get structural AST outline (functions, classes, methods, and line ranges) of a file without reading the entire raw file.
            file_path: Relative repository path of the source file to outline."""
            return self.facade.get_outline(file_path)

        @self.mcp.tool()
        @_wrap
        def get_neighborhood(
            symbol: str, file_path: str = "", direction: str = "both", depth: int = 2
        ) -> dict[str, Any]:
            """Traverse caller/callee and import dependency graph for a symbol or function.
            symbol: Target symbol name or symbol ID to traverse from.
            file_path: Optional file path to disambiguate symbols with identical names across files.
            direction: Traversal direction: 'upstream' (callers), 'downstream' (callees), or 'both' (default).
            depth: Graph traversal distance (default: 2, recommended: 1-3)."""
            return self.facade.get_neighborhood(
                symbol, file_path=file_path or None, direction=direction, depth=depth
            )

        @self.mcp.tool()
        @_wrap
        def get_callers(symbol: str, file_path: str = "") -> dict[str, Any]:
            """Find all upstream callers and functions that depend on this symbol (inbound blast radius).
            symbol: Target symbol name to find incoming callers for.
            file_path: Optional file path to disambiguate symbols with identical names."""
            return self.facade.get_neighborhood(
                symbol=symbol, file_path=file_path or None, direction="upstream", depth=1
            )

        @self.mcp.tool()
        @_wrap
        def get_callees(symbol: str, file_path: str = "") -> dict[str, Any]:
            """Find all downstream functions, symbols, and imports that this symbol calls or depends upon.
            symbol: Target symbol name to find outgoing calls for.
            file_path: Optional file path to disambiguate symbols with identical names."""
            return self.facade.get_neighborhood(
                symbol=symbol, file_path=file_path or None, direction="downstream", depth=1
            )

        @self.mcp.tool()
        @_wrap
        def read_symbol(symbol: str, file_path: str = "") -> dict[str, Any]:
            """Read the exact code lines and docstring of a specific symbol/function without reading the whole file. If multiple candidate files match, candidate paths are returned so you can specify file_path.
            symbol: Exact name of function, class, or method to read.
            file_path: Optional relative file path to select specific file when symbol name is shared."""
            return self.facade.read_symbol(symbol=symbol, file_path=file_path or None)

        @self.mcp.tool()
        @_wrap
        def get_diff(file_path: str = "", staged: bool = False) -> dict[str, Any]:
            """Get raw unified git diff of uncommitted changes. Optionally filter by file_path or inspect staged changes.
            file_path: Optional relative file path to inspect diff for a single file.
            staged: If True, shows staged changes; otherwise shows unstaged working tree changes."""
            return self.facade.get_diff(file_path=file_path, staged=staged)

        @self.mcp.tool()
        @_wrap
        def get_test_recommendations(file_path: str = "") -> dict[str, Any]:
            """Recommend specific pytest test files and commands to execute for a modified file or current git diff.
            file_path: Optional file path to evaluate. If omitted, dirty files in working tree are analyzed."""
            return self.facade.get_test_recommendations(file_path=file_path)

        @self.mcp.tool()
        @_wrap
        def remember(key: str, content: str, summary: str = "") -> dict[str, Any]:
            """Save a working observation, environment fact, or operational rule into persistent memory.
            key: Semantic category key (e.g. 'auth_policy', 'database_schema', 'ci_rule').
            content: Detailed observation or fact to persist.
            summary: Optional concise 1-line summary for rapid preamble inclusion."""
            return self.facade.remember(key, content, summary=summary)

        @self.mcp.tool()
        @_wrap
        def recall(key: str = "", limit: int = 10) -> dict[str, Any]:
            """Recall saved working observations or facts from persistent memory, optionally filtered by topic key.
            key: Optional topic key filter. If omitted, returns most recent memories.
            limit: Maximum number of memories to return (default: 10)."""
            return self.facade.recall(key=key, limit=limit)

        @self.mcp.tool()
        @_wrap
        def get_blast_radius() -> dict[str, Any]:
            """Analyze the blast radius of current uncommitted git changes, identifying modified symbols and impacted callers and tests."""
            return self.facade.get_blast_radius()

        @self.mcp.tool()
        @_wrap
        def get_skeleton(file_path: str) -> dict[str, Any]:
            """Get structural code skeleton of a file (stripping function/method bodies while preserving imports, signatures, types, and docstrings). Saves 80-90% tokens.
            file_path: Relative repository path of the source file to skeletonize."""
            return self.facade.get_skeleton(file_path)

    async def run(self) -> None:
        await self.mcp.run_stdio_async()
