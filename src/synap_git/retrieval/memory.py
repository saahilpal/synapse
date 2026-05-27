from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from synap_git.config import SynapSettings
from synap_git.git.state import GitState
from synap_git.storage.sqlite import SynapStore


@dataclass
class DirtyWarning:
    files: list[str]
    commit: str
    message: str


@dataclass
class InjectionContext:
    project_overview: str
    current_branch: str
    current_commit: str
    dirty_warning: DirtyWarning | None
    recent_commits: list[dict[str, Any]]
    recent_decisions: list[dict[str, Any]]
    active_checkpoint: dict[str, Any] | None
    approved_lessons: list[dict[str, Any]]
    pending_lessons: list[dict[str, Any]]
    architecture_summary: str

    def format_header(self) -> str:
        parts = []
        parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        parts.append(
            f"SYNAP CONTEXT — {self.current_branch} ({self.current_commit[:8] if self.current_commit else 'none'})"
        )
        parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if self.project_overview:
            parts.append(self.project_overview)
        else:
            parts.append("No project overview available.")

        parts.append("")

        if self.active_checkpoint:
            parts.append("ACTIVE CHECKPOINT:")
            parts.append(f"  Working on: {self.active_checkpoint.get('doing', '')}")

            try:
                changed = json.loads(self.active_checkpoint.get("changed_files", "[]"))
                parts.append(f"  Changed files: {', '.join(changed)}")
            except json.JSONDecodeError:
                parts.append(f"  Changed files: {self.active_checkpoint.get('changed_files', '')}")

            parts.append(f"  Next step: {self.active_checkpoint.get('next_step', '')}")
            parts.append("")

        if self.approved_lessons:
            parts.append("APPROVED LESSONS (apply always):")
            for i, lesson in enumerate(self.approved_lessons, 1):
                parts.append(
                    f"  [{i}] {lesson.get('what_failed', '')} -> {lesson.get('why_failed', '')}"
                )
            parts.append("")

        if self.pending_lessons:
            parts.append("PENDING LESSONS (unverified — use with caution):")
            for i, lesson in enumerate(self.pending_lessons, 1):
                parts.append(f"  [{i}] ⚠ {lesson.get('what_failed', '')} — awaiting user review")
            parts.append("")

        if self.recent_decisions:
            parts.append("RECENT DECISIONS:")
            for dec in self.recent_decisions:
                parts.append(f"  [{dec.get('created_at', '')}] {dec.get('content', '')}")
            parts.append("")

        if self.dirty_warning:
            parts.append(
                f"⚠ DIRTY TREE: {len(self.dirty_warning.files)} files modified since {self.dirty_warning.commit}"
            )

        parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(parts)


def check_dirty_tree(git_state: GitState) -> DirtyWarning | None:
    if git_state.is_dirty:
        # We'd get actual files from GitState ideally. Let's return empty for now.
        return DirtyWarning(
            files=[],
            commit=git_state.head_commit[:8] if git_state.head_commit else "unknown",
            message="⚠ Modified files not yet committed. Agent context may not match reported commit.",
        )
    return None


def read_wiki(settings: SynapSettings, filename: str) -> str:
    path = settings.state_path / "wiki" / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def build_injection_context(
    settings: SynapSettings, store: SynapStore, git_state: GitState
) -> InjectionContext:
    branch = git_state.effective_branch

    return InjectionContext(
        project_overview=read_wiki(settings, "overview.md"),
        current_branch=branch,
        current_commit=git_state.head_commit or "unknown",
        dirty_warning=check_dirty_tree(git_state),
        recent_commits=[],
        recent_decisions=store.get_decisions(branch, limit=10),
        active_checkpoint=store.get_latest_checkpoint(branch),
        approved_lessons=store.get_lessons(status="approved"),
        pending_lessons=store.get_lessons(status="pending"),
        architecture_summary=read_wiki(settings, "architecture.md"),
    )
