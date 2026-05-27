from __future__ import annotations

import hashlib
from collections.abc import Iterator

from synap_git.provider.base import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Mock LLM provider returning deterministic replies."""

    def __init__(self, preset_replies: dict[str, str] | None = None) -> None:
        self.preset_replies = preset_replies or {}

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        _ = (model, max_tokens, temperature)
        # Match preset replies if any substring matches
        combined = f"{system_prompt}\n{user_prompt}".lower()
        for pattern, reply in self.preset_replies.items():
            if pattern.lower() in combined:
                return LLMResponse(content=reply, prompt_tokens=10, completion_tokens=10)

        # Default fallback responses based on keywords in prompt
        if "explain" in combined or "how does" in combined:
            content = (
                "Mock Explanation: This subsystem handles core state management. "
                "It uses an append-only event log stored in SQLite and serializes active graph nodes."
            )
        elif "overlay" in combined or "annotate" in combined:
            content = "Mock Overlay: This module is stable and optimized. It implements caching to prevent graph explosion."
        else:
            content = f"Mock LLM generated response for query. Model: {model or 'mock-model'}."

        return LLMResponse(
            content=content,
            prompt_tokens=20,
            completion_tokens=30,
        )

    def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        res = self.generate(
            system_prompt, user_prompt, model=model, max_tokens=max_tokens, temperature=temperature
        )
        yield res.content

    def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        _ = model
        # Deterministic pseudo-embedding based on string md5 hash
        hasher = hashlib.md5(text.encode("utf-8"), usedforsecurity=False)  # noqa: S324
        digest = hasher.digest()
        embedding = []
        for i in range(16):
            # Normalize to [-1.0, 1.0] range
            val = (digest[i] - 128.0) / 128.0
            embedding.append(val)
        # Pad or repeat to match embedding dimensions (e.g. 128 dimensions)
        return embedding * 8

    def count_tokens(self, text: str) -> int:
        return len(text.split())
