from __future__ import annotations

from pathlib import Path


class InputValidator:
    """Validates inputs, restricts file paths to workspace boundaries, and enforces limits."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()

    def validate_safe_path(self, relative_path: str | Path) -> Path:
        """Ensures the path does not traverse outside the repository workspace."""
        requested_path = Path(relative_path)

        # Prevent absolute path traversal if they try to pass /etc/passwd etc.
        if requested_path.is_absolute():
            resolved_path = requested_path.resolve()
        else:
            resolved_path = (self.repo_root / requested_path).resolve()

        try:
            resolved_path.relative_to(self.repo_root)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {relative_path} is outside of repository root."
            )

        return resolved_path

    def validate_limit(self, limit: int, default: int = 20, max_limit: int = 100) -> int:
        """Clamps query result count to safe boundary."""
        if limit <= 0:
            return default
        return min(limit, max_limit)

    def validate_depth(self, depth: int, default: int = 5, max_depth: int = 10) -> int:
        """Clamps traversal depth to prevent stack overflow or DoS."""
        if depth <= 0:
            return default
        return min(depth, max_depth)

    def validate_payload_size(self, data: bytes | str, max_bytes: int = 1_000_000) -> None:
        """Verifies content size is within safe bounds."""
        size = len(data.encode("utf-8") if isinstance(data, str) else data)
        if size > max_bytes:
            raise ValueError(
                f"Payload size {size} bytes exceeds maximum allowed limit of {max_bytes} bytes."
            )
