class IngestionSanitizer:
    """Sanitizes inputs before they are stored or processed."""

    @staticmethod
    def sanitize_note(content: str) -> str:
        """Cleans manual note content."""
        if not content:
            return ""
        if "\x00" in content:
            raise ValueError("Content contains null bytes")
        if len(content) > 1_000_000:
            raise ValueError("Content exceeds maximum length of 1,000,000 characters")
        return content

    @classmethod
    def sanitize_lesson(cls, what_failed: str, why_failed: str) -> tuple[str, str]:
        """Validates and cleans lesson content."""
        return cls.sanitize_note(what_failed), cls.sanitize_note(why_failed)

    @classmethod
    def sanitize_checkpoint(
        cls, doing: str, changed_files: list[str], next_step: str, blockers: str
    ) -> tuple[str, list[str], str, str]:
        """Validates and cleans checkpoint content."""
        clean_doing = cls.sanitize_note(doing)
        clean_files = [cls.sanitize_note(f) for f in changed_files if f]
        clean_next = cls.sanitize_note(next_step) if next_step else ""
        clean_blockers = cls.sanitize_note(blockers) if blockers else ""
        return clean_doing, clean_files, clean_next, clean_blockers
