from __future__ import annotations

import json
import urllib.request
from typing import Any

from synapse.provider.base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """Anthropic API provider implementation."""

    def __init__(self, api_key: str, default_model: str = "claude-3-5-sonnet-latest") -> None:
        self.api_key = api_key
        self.default_model = default_model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        model_name = model or self.default_model
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        payload: dict[str, Any] = {
            "model": model_name,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }

        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=45.0) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))

            content = data["content"][0]["text"]
            usage = data.get("usage", {})
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)
            cached_tokens = usage.get("cache_creation_input_tokens", 0) + usage.get(
                "cache_read_input_tokens", 0
            )

            return LLMResponse(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )
        except Exception as exc:
            raise RuntimeError(f"Anthropic generate failed: {exc}") from exc

    def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        # Anthropic does not have a public embedding endpoint as of mid 2024.
        # Typically developers use Voyage or OpenAI for embeddings when using Anthropic.
        # We will throw a clear error.
        raise NotImplementedError(
            "Anthropic does not provide a native embeddings API. Please configure SYNAPSE_EMBED_PROVIDER=ollama or openai."
        )
