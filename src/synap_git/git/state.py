from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


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

    def state(self) -> GitState:
        try:
            from git import InvalidGitRepositoryError, NoSuchPathError, Repo
        except ImportError as exc:
            raise GitIntegrationError("GitPython is not installed") from exc

        try:
            repo: Any = Repo(self.path, search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError):
            return GitState(repository_path=self.path.resolve(), is_repository=False)

        repository_path = Path(repo.working_tree_dir or self.path).resolve()
        git_dir = Path(repo.git_dir)
        is_detached = bool(repo.head.is_detached)
        branch: str | None
        if is_detached:
            branch = None
        else:
            branch = str(repo.active_branch.name)

        head_commit: str | None = None
        parent_hashes: tuple[str, ...] = ()
        commit_message: str | None = None
        try:
            commit = repo.head.commit
            head_commit = str(commit.hexsha)
            parent_hashes = tuple(str(parent.hexsha) for parent in commit.parents)
            commit_message = str(commit.message).strip()
        except ValueError:
            pass

        return GitState(
            repository_path=repository_path,
            is_repository=True,
            head_commit=head_commit,
            branch=branch,
            is_dirty=bool(repo.is_dirty(untracked_files=True)),
            is_detached=is_detached,
            merge_in_progress=(git_dir / "MERGE_HEAD").exists(),
            rebase_in_progress=(git_dir / "rebase-merge").exists()
            or (git_dir / "rebase-apply").exists(),
            commit_parent_hashes=parent_hashes,
            commit_message=commit_message,
        )

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
