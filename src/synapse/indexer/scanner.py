from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import structlog

logger = structlog.get_logger()

DEFAULT_EXCLUDES = {
    ".git",
    ".synapse",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    ".next",
    ".cache",
    "vendor",
}

MANIFEST_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "Cargo.toml",
    "go.mod",
}

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".md": "markdown",
}


class FolderRole(StrEnum):
    SOURCE = "source"
    TESTS = "tests"
    DOCS = "docs"
    CONFIG = "config"
    BUILD = "build"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FileObservation:
    path: Path
    relative_path: str
    size_bytes: int
    content_hash: str
    language: str | None
    folder_role: FolderRole
    is_manifest: bool = False
    git_oid: str | None = None


@dataclass(frozen=True)
class ManifestObservation:
    path: str
    kind: str
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepositoryScan:
    repository_path: Path
    files: tuple[FileObservation, ...]
    manifests: tuple[ManifestObservation, ...]
    language_counts: dict[str, int] = field(default_factory=dict)
    folder_counts: dict[str, int] = field(default_factory=dict)

    @property
    def dependencies(self) -> tuple[str, ...]:
        names: set[str] = set()
        for manifest in self.manifests:
            names.update(manifest.dependencies)
        return tuple(sorted(names))

    def markdown_files(self) -> tuple[FileObservation, ...]:
        return tuple(file for file in self.files if file.language == "markdown")


class GitIgnoreSpec:
    """Simple and robust parser for .gitignore compliance."""

    def __init__(self, base_dir: Path, lines: list[str]) -> None:
        self.base_dir = base_dir.resolve()
        self.rules: list[tuple[bool, re.Pattern[str], bool]] = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            is_negation = False
            if line.startswith("!"):
                is_negation = True
                line = line[1:]

            directory_only = False
            if line.endswith("/"):
                directory_only = True
                line = line[:-1]

            regex = self._glob_to_regex(line)
            try:
                pattern = re.compile(regex)
                self.rules.append((is_negation, pattern, directory_only))
            except re.error:
                continue

    def _glob_to_regex(self, glob: str) -> str:
        leading_slash = glob.startswith("/")
        if leading_slash:
            glob = glob[1:]

        parts = []
        i = 0
        n = len(glob)
        while i < n:
            c = glob[i]
            if c == "*":
                if i + 1 < n and glob[i + 1] == "*":
                    parts.append(".*")
                    i += 2
                    if i < n and glob[i] == "/":
                        i += 1
                else:
                    parts.append("[^/]*")
                    i += 1
            elif c == "?":
                parts.append("[^/]")
                i += 1
            elif c == "/":
                parts.append("/")
                i += 1
            elif c in "\\^$.|?*+()[]{}":
                parts.append("\\" + c)
                i += 1
            else:
                parts.append(c)
                i += 1

        regex = "".join(parts)
        if leading_slash:
            return f"^{regex}(/|$)"
        else:
            return f"(^|/){regex}(/|$)"

    def matches(self, path: Path, is_dir: bool = False) -> bool:
        try:
            rel_path = path.resolve().relative_to(self.base_dir)
        except ValueError:
            return False

        parts = rel_path.parts
        ignored = False
        for i in range(1, len(parts) + 1):
            sub_path = Path(*parts[:i])
            sub_is_dir = (i < len(parts)) or is_dir
            sub_rel_path = sub_path.as_posix()

            for is_negation, pattern, dir_only in self.rules:
                if dir_only and not sub_is_dir:
                    continue
                if pattern.search(sub_rel_path):
                    ignored = not is_negation
        return ignored


class RepositoryScanner:
    """Fast structural scanner with deterministic exclusion and manifest discovery."""

    def __init__(
        self,
        *,
        repository_path: Path,
        excludes: set[str] | None = None,
        max_file_bytes: int = 1_000_000,
    ) -> None:
        self.repository_path = repository_path.resolve()
        self.excludes = excludes or DEFAULT_EXCLUDES
        self.max_file_bytes = max_file_bytes
        self.gitignore = None

        gitignore_path = self.repository_path / ".gitignore"
        if gitignore_path.exists():
            try:
                lines = gitignore_path.read_text(encoding="utf-8").splitlines()
                self.gitignore = GitIgnoreSpec(self.repository_path, lines)
            except Exception as e:
                logger.warning("failed_to_load_gitignore", error=str(e))

    async def scan_async(self) -> RepositoryScan:
        return await asyncio.to_thread(self.scan)

    def scan(self) -> RepositoryScan:
        files: list[FileObservation] = []
        manifests: list[ManifestObservation] = []

        paths: list[Path] = []
        try:
            result = subprocess.run(  # noqa: S603
                ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"],  # noqa: S607
                cwd=self.repository_path,
                capture_output=True,
                check=True,
            )
            for rel_path in result.stdout.split(b"\0"):
                if rel_path:
                    try:
                        paths.append(self.repository_path / rel_path.decode("utf-8"))
                    except UnicodeDecodeError:
                        pass
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to rglob if not a git repository
            paths = list(self.repository_path.rglob("*"))

        for path in paths:
            if not path.is_file():
                continue
            if self._excluded(path):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > self.max_file_bytes:
                continue
            if _is_binary_file(path):
                logger.debug("Skipped binary file", path=path.name)
                continue

            try:
                relative_path = path.relative_to(self.repository_path).as_posix()
                path.resolve().relative_to(self.repository_path)
            except (ValueError, OSError):
                continue
            content_hash = _hash_file(path)
            language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
            folder_role = self._classify_folder(relative_path)
            is_manifest = path.name in MANIFEST_NAMES
            observation = FileObservation(
                path=path,
                relative_path=relative_path,
                size_bytes=stat.st_size,
                content_hash=content_hash,
                language=language,
                folder_role=folder_role,
                is_manifest=is_manifest,
            )
            files.append(observation)
            if is_manifest:
                manifests.append(self._read_manifest(path, relative_path))

        language_counts: dict[str, int] = {}
        folder_counts: dict[str, int] = {}
        for file in files:
            if file.language:
                language_counts[file.language] = language_counts.get(file.language, 0) + 1
            folder_counts[file.folder_role.value] = folder_counts.get(file.folder_role.value, 0) + 1
        return RepositoryScan(
            repository_path=self.repository_path,
            files=tuple(files),
            manifests=tuple(manifests),
            language_counts=dict(sorted(language_counts.items())),
            folder_counts=dict(sorted(folder_counts.items())),
        )

    def _excluded(self, path: Path) -> bool:
        try:
            parts = path.relative_to(self.repository_path).parts
        except ValueError:
            return True
        if any(part in self.excludes for part in parts):
            return True
        if self.gitignore and self.gitignore.matches(path, is_dir=path.is_dir()):
            return True
        return False

    def _classify_folder(self, relative_path: str) -> FolderRole:
        parts = set(Path(relative_path).parts)
        lower = relative_path.lower()
        if "docs" in parts or lower.endswith(".md"):
            return FolderRole.DOCS
        if "tests" in parts or "test" in parts or lower.startswith("test_"):
            return FolderRole.TESTS
        if any(part in parts for part in {"src", "lib", "app", "cmd", "pkg"}):
            return FolderRole.SOURCE
        if relative_path.endswith((".toml", ".json", ".yaml", ".yml", ".ini", ".cfg")):
            return FolderRole.CONFIG
        if any(part in parts for part in {"build", "dist", "target"}):
            return FolderRole.BUILD
        return FolderRole.UNKNOWN

    def _read_manifest(self, path: Path, relative_path: str) -> ManifestObservation:
        try:
            if path.name == "pyproject.toml":
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                dependencies = tuple(_python_dependencies(data))
                return ManifestObservation(relative_path, "python", dependencies)
            if path.name == "requirements.txt":
                return ManifestObservation(relative_path, "python", tuple(_requirements(path)))
            if path.name == "package.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                dependencies = tuple(
                    sorted({*data.get("dependencies", {}), *data.get("devDependencies", {})})
                )
                return ManifestObservation(relative_path, "javascript", dependencies)
            if path.name == "Cargo.toml":
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                dependencies = tuple(sorted(data.get("dependencies", {}).keys()))
                return ManifestObservation(relative_path, "rust", dependencies)
            if path.name == "go.mod":
                return ManifestObservation(relative_path, "go", tuple(_go_dependencies(path)))
        except Exception:
            return ManifestObservation(relative_path, "unknown", ())
        return ManifestObservation(relative_path, "unknown", ())


def _is_binary_file(path: Path) -> bool:
    try:
        # Check extensions first
        binary_extensions = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".ico",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".tgz",
            ".rar",
            ".7z",
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".bin",
            ".dat",
            ".db",
            ".sqlite",
            ".sqlite3",
            ".woff",
            ".woff2",
            ".eot",
            ".ttf",
            ".mp4",
            ".mp3",
            ".wav",
            ".avi",
            ".mov",
            ".flac",
            ".ogg",
            ".webm",
            ".mkv",
            ".class",
            ".o",
            ".a",
            ".out",
            ".pyc",
            ".pyd",
            ".pyo",
        }
        if path.suffix.lower() in binary_extensions:
            return True

        with path.open("rb") as f:
            chunk = f.read(1024)
            if not chunk:
                return False
            if b"\x00" in chunk:
                return True

            control_count = 0
            for byte in chunk:
                if byte < 32 and byte not in (9, 10, 13):
                    control_count += 1
            if len(chunk) > 0 and (control_count / len(chunk)) > 0.1:
                return True
    except Exception:
        return True
    return False


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _python_dependencies(data: dict[str, object]) -> list[str]:
    project = data.get("project")
    names: set[str] = set()
    if isinstance(project, dict):
        dependencies = project.get("dependencies")
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if isinstance(dependency, str):
                    names.add(_dependency_name(dependency))
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    for dependency in values:
                        if isinstance(dependency, str):
                            names.add(_dependency_name(dependency))
    return sorted(name for name in names if name)


def _requirements(path: Path) -> list[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or cleaned.startswith("-"):
            continue
        names.add(_dependency_name(cleaned))
    return sorted(names)


def _go_dependencies(path: Path) -> list[str]:
    names: set[str] = set()
    in_require_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block and cleaned == ")":
            in_require_block = False
            continue
        if cleaned.startswith("require "):
            parts = cleaned.split()
            if len(parts) >= 2:
                names.add(parts[1])
        elif in_require_block and cleaned:
            names.add(cleaned.split()[0])
    return sorted(names)


def _dependency_name(requirement: str) -> str:
    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
        if separator in requirement:
            return requirement.split(separator, 1)[0].strip()
    return requirement.strip()
