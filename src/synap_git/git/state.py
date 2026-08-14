from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class GitIntegrationError(RuntimeError):
    """Raised when Git state cannot be inspected."""


class GitChangeKind(StrEnum):
    INITIAL = "initial"
    COMMIT = "commit"
    CHECKOUT = "checkout"
    BRANCH = "branch"
    MERGE = "merge"
    REBASE = "rebase"
    REVERT = "revert"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class GitState:
    repository_path: Path
    is_repository: bool
    head_commit: str | None = None
    branch: str | None = None
    is_dirty: bool = False
    is_detached: bool = False
    merge_in_progress: bool = False
    rebase_in_progress: bool = False
    commit_parent_hashes: tuple[str, ...] = ()
    commit_message: str | None = None

    @property
    def effective_branch(self) -> str:
        return self.branch or "detached"


@dataclass(frozen=True)
class GitChange:
    kind: GitChangeKind
    previous: GitState | None
    current: GitState


class GitRepository:
    """Thin GitPython-backed reader for repository lineage state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._cached_fingerprint: tuple[float, float, float] | None = None
        self._cached_state: GitState | None = None

    def invalidate_cache(self) -> None:
        self._cached_fingerprint = None
        self._cached_state = None

    def _get_git_fingerprint(self, git_dir: Path) -> tuple[float, float, float]:
        try:
            head_mtime = (git_dir / "HEAD").stat().st_mtime
        except OSError:
            head_mtime = 0.0
        try:
            index_mtime = (git_dir / "index").stat().st_mtime
        except OSError:
            index_mtime = 0.0
        try:
            refs_mtime = (git_dir / "refs").stat().st_mtime
        except OSError:
            refs_mtime = 0.0
        return (head_mtime, index_mtime, refs_mtime)

    def state(self, *, force: bool = False) -> GitState:
        try:
            repository_path = self.path.resolve()
            git_dir = repository_path / ".git"
            if not git_dir.exists():
                return GitState(repository_path=repository_path, is_repository=False)

            if not force and self._cached_state is not None:
                fp = self._get_git_fingerprint(git_dir)
                if fp == self._cached_fingerprint:
                    return self._cached_state

            is_detached = False
            branch = None
            head_commit = None
            parent_hashes: tuple[str, ...] = ()
            commit_message = None

            try:
                branch = subprocess.run(
                    ["git", "symbolic-ref", "--short", "--quiet", "HEAD"],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
            except subprocess.CalledProcessError:
                is_detached = True
                branch = None

            if branch == "HEAD":
                branch = None

            try:
                head_commit = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
            except subprocess.CalledProcessError:
                head_commit = None

            try:
                is_dirty = (
                    subprocess.run(
                        ["git", "status", "--porcelain", "--untracked-files"],
                        cwd=repository_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout
                    != ""
                )
            except subprocess.CalledProcessError:
                is_dirty = False

            state_obj = GitState(
                repository_path=repository_path,
                is_repository=True,
                head_commit=head_commit,
                branch=branch,
                is_dirty=is_dirty,
                is_detached=is_detached,
                merge_in_progress=(git_dir / "MERGE_HEAD").exists(),
                rebase_in_progress=(git_dir / "rebase-merge").exists()
                or (git_dir / "rebase-apply").exists(),
                commit_parent_hashes=parent_hashes,
                commit_message=commit_message,
            )
            self._cached_fingerprint = self._get_git_fingerprint(git_dir)
            self._cached_state = state_obj
            return state_obj
        except Exception as exc:
            raise GitIntegrationError("Git state could not be determined") from exc

    @staticmethod
    def classify(previous: GitState | None, current: GitState) -> GitChange:
        if previous is None:
            return GitChange(kind=GitChangeKind.INITIAL, previous=None, current=current)
        if current.rebase_in_progress and not previous.rebase_in_progress:
            return GitChange(kind=GitChangeKind.REBASE, previous=previous, current=current)
        if current.merge_in_progress and not previous.merge_in_progress:
            return GitChange(kind=GitChangeKind.MERGE, previous=previous, current=current)
        if previous.branch != current.branch:
            return GitChange(kind=GitChangeKind.BRANCH, previous=previous, current=current)
        if previous.head_commit != current.head_commit:
            message = current.commit_message or ""
            if message.startswith("Revert ") and not message.startswith('Revert "Revert "'):
                return GitChange(kind=GitChangeKind.REVERT, previous=previous, current=current)

            try:
                from git import Repo

                repo = Repo(current.repository_path)
                curr_commit = repo.head.commit
                curr_tree = curr_commit.tree.hexsha
                is_revert = False
                for parent in curr_commit.parents:
                    for ancestor in repo.iter_commits(parent, max_count=20):
                        if ancestor.tree.hexsha == curr_tree:
                            is_revert = True
                            break
                    if is_revert:
                        break
                if is_revert:
                    return GitChange(kind=GitChangeKind.REVERT, previous=previous, current=current)
            except Exception as e:
                import structlog

                structlog.get_logger().error("suppressed_error_caught", error=str(e))

            if len(current.commit_parent_hashes) > 1:
                return GitChange(kind=GitChangeKind.MERGE, previous=previous, current=current)
            return GitChange(kind=GitChangeKind.COMMIT, previous=previous, current=current)
        if previous.is_detached != current.is_detached:
            return GitChange(kind=GitChangeKind.CHECKOUT, previous=previous, current=current)
        return GitChange(kind=GitChangeKind.UNCHANGED, previous=previous, current=current)
