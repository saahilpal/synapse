import re
from typing import Any


class SecretRedactor:
    """Redacts secrets, API keys, and tokens from text and dictionaries."""

    # Common secret patterns
    SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{32,}", re.IGNORECASE),  # OpenAI, Anthropic, etc.
        re.compile(r"Bearer\s+[a-zA-Z0-9\-\._~\+\/]+", re.IGNORECASE),  # Bearer tokens
        re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),  # AWS Access Key
        re.compile(r"gh[p|u|s|o]_[a-zA-Z0-9]{36}", re.IGNORECASE),  # GitHub tokens
        re.compile(r"xox[baprs]-[a-zA-Z0-9]+", re.IGNORECASE),  # Slack tokens
        # Env-var style assignments
        re.compile(r"(?i)(?:API_KEY|PASSWORD|SECRET|TOKEN)\s*=\s*[\"']?([^\s\"']+)[\"']?"),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        if not text:
            return text

        redacted_text = text
        for pattern in cls.SECRET_PATTERNS:

            def replacer(match: re.Match[str]) -> str:
                # If there's a capture group (like in the env-var pattern), replace just the group
                if match.groups():
                    full = match.group(0)
                    val = match.group(1)
                    return str(full.replace(val, "[REDACTED]"))
                return "[REDACTED]"

            redacted_text = pattern.sub(replacer, redacted_text)
        return redacted_text

    @classmethod
    def redact_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact strings in a dictionary."""
        result: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, dict):
                result[k] = cls.redact_dict(v)
            elif isinstance(v, list):
                result[k] = [
                    cls.redact_dict(item)
                    if isinstance(item, dict)
                    else (cls.redact(item) if isinstance(item, str) else item)
                    for item in v
                ]
            elif isinstance(v, str):
                result[k] = cls.redact(v)
            else:
                result[k] = v
        return result
