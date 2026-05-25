from __future__ import annotations

import hashlib
import hmac
import re


class SecurityError(ValueError):
    """Raised when security verification or sanitization fails."""


class IngestionSanitizer:
    """Hardens ingestion processes against malicious prompt injections and tampered hashes."""

    # Common prompt injection patterns
    INJECTION_regexes = [
        re.compile(r"ignore\s+(?:previous\s+)?instructions", re.IGNORECASE),
        re.compile(r"override\s+(?:the\s+)?instructions", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+a\s+\w+", re.IGNORECASE),
        re.compile(r"dan\s+mode", re.IGNORECASE),
        re.compile(r"<script.*?>", re.IGNORECASE),
        re.compile(r"javascript:", re.IGNORECASE),
        re.compile(r"system\s+prompt\s+bypass", re.IGNORECASE),
    ]

    def scan_for_injections(self, text: str) -> tuple[bool, str | None]:
        """Scan input text for common prompt injection or malicious markup patterns.

        Returns (is_safe, violating_pattern_description).
        """
        for regex in self.INJECTION_regexes:
            if regex.search(text):
                return False, f"Malicious input pattern detected: '{regex.pattern}'"
        return True, None

    def sanitize_note(self, content: str) -> str:
        """Sanitizes manual notes, raising SecurityError if prompt injection is found."""
        is_safe, reason = self.scan_for_injections(content)
        if not is_safe:
            raise SecurityError(reason)
        # Redact/strip HTML tags for rendering safety
        clean = re.sub(r"<[^>]*>", "", content)
        return clean

    def sign_context_hash(self, context_hash: str, secret_key: bytes) -> str:
        """Generate a cryptographically secure signature for a context hash using HMAC-SHA256."""
        if not secret_key:
            secret_key = b"default_synapse_local_signing_key_secret_12345"
        return hmac.new(secret_key, context_hash.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_context_signature(
        self, context_hash: str, signature: str, secret_key: bytes
    ) -> bool:
        """Verify the cryptographic signature of a context hash."""
        if not secret_key:
            secret_key = b"default_synapse_local_signing_key_secret_12345"
        expected = self.sign_context_hash(context_hash, secret_key)
        return hmac.compare_digest(expected, signature)
