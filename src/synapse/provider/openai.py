from __future__ import annotations

import json
import urllib.request
from typing import Any

from synapse.provider.base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""

    def __init__(self, api_key: str, default_model: str = "gpt-4o-mini") -> None:
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
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choice = data["choices"][0]["message"]
            usage = data.get("usage", {})
            return LLMResponse(
                content=str(choice["content"]),
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI generate failed: {exc}") from exc

    def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        model_name = model or "text-embedding-3-small"
        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {"input": text, "model": model_name}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            embedding = data["data"][0]["embedding"]
            return [float(x) for x in embedding]
        except Exception as exc:
            raise RuntimeError(f"OpenAI embed failed: {exc}") from exc
