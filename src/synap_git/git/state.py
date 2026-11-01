from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import structlog

logger = structlog.get_logger()


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
class SymbolLineageRecord:
    commit_hash: str
    author_name: str
    author_email: str
    timestamp: int
    message: str


@dataclass(frozen=True)
class GitState:
    repository_path: Path
    is_repository: bool
    head_commit: str | None = None
    branch: str | None = None
    is_dirty: bool = False
    dirty_files: tuple[str, ...] = ()
    is_detached: bool = False
    merge_in_progress: bool = False
    rebase_in_progress: bool = False
    bisect_in_progress: bool = False
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
    """Reader for Git repository lineage, worktree, and branch state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._cached_fingerprint: tuple[float, float, float] | None = None
        self._cached_state: GitState | None = None

    @property
    def repository_path(self) -> Path:
        return self.path

    def invalidate_cache(self) -> None:
        self._cached_fingerprint = None
        self._cached_state = None

    @staticmethod
    def resolve_git_dir(repository_path: Path) -> tuple[Path, Path] | None:
        """
        Resolves (git_dir, common_dir) for a repository or worktree.
        Returns None if repository_path is not inside or at a git repository.
        """
        dot_git = repository_path / ".git"
        if not dot_git.exists():
            return None
        if dot_git.is_file():
            try:
                content = dot_git.read_text(encoding="utf-8").strip()
                if content.startswith("gitdir:"):
                    raw = content.split("gitdir:", 1)[1].strip()
                    gdir = Path(raw)
                    if not gdir.is_absolute():
                        gdir = (dot_git.parent / gdir).resolve()

                    commondir_file = gdir / "commondir"
                    if commondir_file.exists():
                        common_raw = commondir_file.read_text(encoding="utf-8").strip()
                        cdir = Path(common_raw)
                        if not cdir.is_absolute():
                            cdir = (gdir / cdir).resolve()
                    else:
                        cdir = gdir
                    return (gdir, cdir)
            except OSError as err:
                logger.warning("gitdir_resolve_failed", path=str(dot_git), error=str(err))
                return None
        elif dot_git.is_dir():
            return (dot_git, dot_git)
        return None

    @staticmethod
    def find_root(path: Path) -> Path | None:
        """Finds the root repository directory by traversing parent directories."""
        current = path.resolve()
        for candidate in [current, *current.parents]:
            if (candidate / ".git").exists():
                return candidate
        return None

    def _get_git_fingerprint(self, git_dir: Path, common_dir: Path) -> tuple[float, float, float]:
        try:
            head_mtime = (git_dir / "HEAD").stat().st_mtime
        except OSError:
            head_mtime = 0.0
        try:
            index_mtime = (git_dir / "index").stat().st_mtime
        except OSError:
            index_mtime = 0.0
        try:
            refs_path = common_dir / "refs"
            refs_mtime = refs_path.stat().st_mtime
        except OSError:
            try:
                refs_mtime = (common_dir / "packed-refs").stat().st_mtime
            except OSError:
                refs_mtime = 0.0
        return (head_mtime, index_mtime, refs_mtime)

    def state(self, *, force: bool = False, include_untracked: bool = True) -> GitState:
        try:
            repository_path = self.path.resolve()
            dirs = self.resolve_git_dir(repository_path)
            if dirs is None:
                return GitState(repository_path=repository_path, is_repository=False)

            git_dir, common_dir = dirs

            if not force and self._cached_state is not None:
                fp = self._get_git_fingerprint(git_dir, common_dir)
                if fp == self._cached_fingerprint:
                    return self._cached_state

            is_detached = False
            branch = None
            head_commit = None
            parent_hashes: tuple[str, ...] = ()
            commit_message = None

            try:
                branch_proc = subprocess.run(
                    ["git", "symbolic-ref", "--short", "--quiet", "HEAD"],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                branch = branch_proc.stdout.strip()
            except subprocess.CalledProcessError:
                is_detached = True
                branch = None

            if branch == "HEAD":
                branch = None

            try:
                head_proc = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                head_commit = head_proc.stdout.strip()
            except subprocess.CalledProcessError:
                head_commit = None

            if head_commit:
                try:
                    msg_proc = subprocess.run(
                        ["git", "log", "-1", "--format=%B", "HEAD"],
                        cwd=repository_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    commit_message = msg_proc.stdout.strip()
                except subprocess.CalledProcessError:
                    commit_message = None

                try:
                    parents_raw = subprocess.run(
                        ["git", "rev-parse", "HEAD^@"],
                        cwd=repository_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout.strip()
                    if parents_raw:
                        parent_hashes = tuple(parents_raw.splitlines())
                except subprocess.CalledProcessError:
                    parent_hashes = ()

            dirty_files: list[str] = []
            is_dirty = False
            try:
                status_cmd = ["git", "status", "--porcelain"]
                if not include_untracked:
                    status_cmd.append("--untracked-files=no")
                else:
                    status_cmd.append("--untracked-files=all")

                proc = subprocess.run(
                    status_cmd,
                    cwd=repository_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                lines = [line_item for line_item in proc.stdout.splitlines() if line_item.strip()]
                if lines:
                    is_dirty = True
                    for line in lines:
                        if len(line) > 3:
                            rel_p = line[3:].strip()
                            # Handle renames: "R  old.py -> new.py"
                            if " -> " in rel_p:
                                rel_p = rel_p.split(" -> ", 1)[1].strip()
                            # Handle quotes for paths with spaces
                            if rel_p.startswith('"') and rel_p.endswith('"'):
                                rel_p = rel_p[1:-1]
                            dirty_files.append(rel_p)
            except subprocess.CalledProcessError as e:
                logger.warning("git_status_porcelain_failed", error=str(e))
                is_dirty = False

            state_obj = GitState(
                repository_path=repository_path,
                is_repository=True,
                head_commit=head_commit,
                branch=branch,
                is_dirty=is_dirty,
                dirty_files=tuple(dirty_files),
                is_detached=is_detached,
                merge_in_progress=(git_dir / "MERGE_HEAD").exists(),
                rebase_in_progress=(git_dir / "rebase-merge").exists()
                or (git_dir / "rebase-apply").exists(),
                bisect_in_progress=(git_dir / "BISECT_LOG").exists()
                or (git_dir / "BISECT_START").exists(),
                commit_parent_hashes=parent_hashes,
                commit_message=commit_message,
            )
            self._cached_fingerprint = self._get_git_fingerprint(git_dir, common_dir)
            self._cached_state = state_obj
            return state_obj
        except Exception as exc:
            logger.error("git_state_failed", error=str(exc))
            raise GitIntegrationError("Git state could not be determined") from exc

    def get_dirty_diff_ranges(
        self, include_untracked: bool = True
    ) -> dict[str, list[tuple[int, int]]]:
        """
        Extract modified line intervals for uncommitted changes.
        Returns a mapping of relative file path to list of (start_line, end_line) ranges.
        Handles tracked modifications (staged/unstaged), renames, and untracked files.
        """
        diff_map: dict[str, list[tuple[int, int]]] = {}
        repo_path = self.path.resolve()

        try:
            # 1. Compare against HEAD; fallback to empty-tree if repository has no commits yet
            diff_cmd = ["git", "diff", "-U0", "HEAD"]
            res = subprocess.run(
                diff_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if res.returncode != 0:
                # Fallback for fresh repos: compare staged against empty tree, then working tree
                res = subprocess.run(
                    ["git", "diff", "-U0", "4b825dc642cb6eb9a060e54bf8d69288fbee4904"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if res.returncode != 0:
                    res = subprocess.run(
                        ["git", "diff", "-U0"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=5.0,
                    )

            current_file: str | None = None
            old_file: str | None = None
            file_re = re.compile(r"^diff --git (?:a/|\"a/)(.*?)[\"]? (?:b/|\"b/)(.*?)[\"]?$")
            hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

            for line in res.stdout.splitlines():
                m_file = file_re.match(line)
                if m_file:
                    old_path = m_file.group(1).rstrip('"')
                    new_path = m_file.group(2).rstrip('"')
                    current_file = new_path
                    old_file = old_path
                    if current_file not in diff_map:
                        diff_map[current_file] = []
                    # Also register old_file for renames so database symbol lookups match
                    if old_file and old_file != current_file and old_file not in diff_map:
                        diff_map[old_file] = []
                    continue

                if current_file:
                    m_hunk = hunk_re.match(line)
                    if m_hunk:
                        old_start = int(m_hunk.group(1))
                        old_count = int(m_hunk.group(2)) if m_hunk.group(2) is not None else 1
                        new_start = int(m_hunk.group(3))
                        new_count = int(m_hunk.group(4)) if m_hunk.group(4) is not None else 1

                        # In indexed SQLite database, symbols reside at old_start (HEAD).
                        # In the working tree, additions/changes reside at new_start.
                        # Include both so blast radius accurately catches deleted/modified symbols
                        # and newly modified regions.
                        if old_count > 0:
                            diff_map[current_file].append((old_start, old_start + old_count - 1))
                            if old_file and old_file != current_file:
                                diff_map[old_file].append((old_start, old_start + old_count - 1))
                        if new_count > 0:
                            diff_map[current_file].append((new_start, new_start + new_count - 1))

            # 2. Include untracked files if requested
            if include_untracked:
                proc = subprocess.run(
                    ["git", "status", "--porcelain", "--untracked-files=all"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if proc.returncode == 0:
                    for s_line in proc.stdout.splitlines():
                        if s_line.startswith("?? "):
                            u_path = s_line[3:].strip().strip('"')
                            p = repo_path / u_path
                            if p.is_file():
                                try:
                                    line_count = len(
                                        p.read_text(encoding="utf-8", errors="ignore").splitlines()
                                    )
                                    diff_map[u_path] = [(1, max(1, line_count))]
                                except OSError:
                                    pass
        except Exception as e:
            logger.error("get_dirty_diff_ranges_failed", error=str(e), path=str(repo_path))

        return diff_map

    def get_symbol_lineage(
        self,
        file_path: str,
        symbol_name: str | None = None,
        line_range: tuple[int, int] | None = None,
        max_commits: int = 10,
    ) -> list[SymbolLineageRecord]:
        """
        Track commit history lineage for a symbol or line interval across Git history.
        Uses git log -L (exact line range) with fallback to git log -S (pickaxe symbol search).
        """
        records: list[SymbolLineageRecord] = []
        clean_path = file_path.strip().lstrip("/")
        repo_path = self.path.resolve()

        # Strategy 1: Exact line range via git log -L
        if line_range is not None:
            s_line, e_line = line_range
            cmd = [
                "git",
                "log",
                "-n",
                str(max_commits),
                "-L",
                f"{s_line},{e_line}:{clean_path}",
                "--no-patch",
                "--format=%H%x00%an%x00%ae%x00%at%x00%s",
            ]
            try:
                res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
                for line in res.stdout.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split("\x00")
                    if len(parts) >= 5:
                        records.append(
                            SymbolLineageRecord(
                                commit_hash=parts[0],
                                author_name=parts[1],
                                author_email=parts[2],
                                timestamp=int(parts[3]),
                                message=parts[4],
                            )
                        )
                if records:
                    return records
            except subprocess.CalledProcessError as e:
                logger.debug(
                    "git_log_range_fallback_to_pickaxe",
                    path=clean_path,
                    range=line_range,
                    error=str(e),
                )

        # Strategy 2: Pickaxe symbol search via git log -S
        if symbol_name:
            cmd = [
                "git",
                "log",
                "-n",
                str(max_commits),
                "--follow",
                "-S",
                symbol_name,
                "--format=%H%x00%an%x00%ae%x00%at%x00%s",
                "--",
                clean_path,
            ]
            try:
                res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
                for line in res.stdout.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split("\x00")
                    if len(parts) >= 5:
                        records.append(
                            SymbolLineageRecord(
                                commit_hash=parts[0],
                                author_name=parts[1],
                                author_email=parts[2],
                                timestamp=int(parts[3]),
                                message=parts[4],
                            )
                        )
            except subprocess.CalledProcessError as e:
                logger.warning(
                    "git_log_pickaxe_failed",
                    path=clean_path,
                    symbol=symbol_name,
                    error=str(e),
                )

        return records

    @staticmethod
    def classify(previous: GitState | None, current: GitState) -> GitChange:
        if previous is None:
            return GitChange(kind=GitChangeKind.INITIAL, previous=None, current=current)
        if current.rebase_in_progress and not previous.rebase_in_progress:
            return GitChange(kind=GitChangeKind.REBASE, previous=previous, current=current)
        if current.merge_in_progress and not previous.merge_in_progress:
            return GitChange(kind=GitChangeKind.MERGE, previous=previous, current=current)

        # Checkout transitions between attached branch and detached HEAD
        if previous.is_detached != current.is_detached:
            return GitChange(kind=GitChangeKind.CHECKOUT, previous=previous, current=current)

        if previous.branch != current.branch:
            return GitChange(kind=GitChangeKind.BRANCH, previous=previous, current=current)

        if previous.head_commit != current.head_commit:
            # If both were detached and head moved without previous commit being parent, it is a checkout (e.g. git bisect or checkout HEAD~1)
            if previous.is_detached and current.is_detached:
                if (
                    previous.head_commit
                    and previous.head_commit not in current.commit_parent_hashes
                ):
                    return GitChange(
                        kind=GitChangeKind.CHECKOUT, previous=previous, current=current
                    )

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
                logger.error("suppressed_error_caught", error=str(e))

            if len(current.commit_parent_hashes) > 1:
                return GitChange(kind=GitChangeKind.MERGE, previous=previous, current=current)
            return GitChange(kind=GitChangeKind.COMMIT, previous=previous, current=current)

        return GitChange(kind=GitChangeKind.UNCHANGED, previous=previous, current=current)
