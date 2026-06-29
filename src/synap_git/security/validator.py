from pathlib import Path


class InputValidator:
    """Validates inputs to ensure they are within safe bounds and scope."""

    @staticmethod
    def validate_path(path: str | Path, repo_root: str | Path) -> Path:
        """Ensures the path is within the repo_root."""
        target = Path(path).resolve()
        root = Path(repo_root).resolve()

        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Path traversal detected: {path} is outside {repo_root}")
        return target

    @staticmethod
    def clamp_int(value: int, min_val: int, max_val: int) -> int:
        """Clamps an integer to a specified range."""
        return max(min_val, min(value, max_val))

    @staticmethod
    def validate_query(query: str, max_length: int = 10000) -> str:
        """Validates search queries to prevent abuse."""
        if not query:
            return ""
        if len(query) > max_length:
            raise ValueError(f"Query exceeds maximum length of {max_length}")
        if "\x00" in query:
            raise ValueError("Query contains null bytes")
        return query
