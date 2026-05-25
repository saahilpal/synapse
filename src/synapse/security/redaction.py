from __future__ import annotations

import re
from typing import Any, TypeVar, cast

# Regex patterns for sensitive keys
SENSITIVE_KEY_RE = re.compile(
    r"(?:password|passwd|secret|token|api_key|apikey|private_key|client_secret|access_token|credential|auth_token|auth_key|jwt)",
    re.IGNORECASE,
)

# Regex patterns for credential values
CREDENTIAL_PATTERNS = [
    # AWS Access Key ID
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # GitHub Tokens
    re.compile(r"\bgh[oprs]_[a-zA-Z0-9]{36}\b"),
    re.compile(r"\bgithub_pat_[a-zA-Z0-9]{82}\b"),
    # General Slack Token
    re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b"),
    # SSH Private Key Header
    re.compile(r"-----BEGIN [A-Z\s]+ PRIVATE KEY-----"),
    # Database URIs with credentials
    re.compile(r"[a-zA-Z0-9+.-]+://[^/\s:]+:[^/\s@]+@[^/\s@]+:[0-9]+[^/\s]*"),
]

T = TypeVar("T")


class SecretRedactor:
    """Detects and redacts credentials, secrets, and sensitive information from data."""

    def redact(self, data: T) -> T:
        if isinstance(data, dict):
            return cast(T, {str(k): self._redact_dict_item(k, v) for k, v in data.items()})
        elif isinstance(data, list):
            return cast(T, [self.redact(item) for item in data])
        elif isinstance(data, tuple):
            return cast(T, tuple(self.redact(item) for item in data))
        elif isinstance(data, set):
            return cast(T, {self.redact(item) for item in data})
        elif isinstance(data, str):
            return cast(T, self._redact_string(data))
        return data

    def _redact_dict_item(self, key: Any, value: Any) -> Any:
        # Check if the key name is sensitive
        if isinstance(key, str) and SENSITIVE_KEY_RE.search(key):
            return "[REDACTED]"
        return self.redact(value)

    def _redact_string(self, val: str) -> str:
        # Check against value pattern-based secrets
        result = val
        for pattern in CREDENTIAL_PATTERNS:
            # If the pattern is database URI, we might want to redact only the password part
            if "://" in pattern.pattern and "@" in pattern.pattern:
                matches = pattern.findall(result)
                for match in matches:
                    redacted_uri = re.sub(r":([^/\s@]+)@", ":[REDACTED]@", match)
                    result = result.replace(match, redacted_uri)
            else:
                result = pattern.sub("[REDACTED]", result)
        return result
