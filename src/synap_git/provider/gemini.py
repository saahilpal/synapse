from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from synap_git.provider.base import LLMProvider, LLMResponse


def _with_retries(func: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        attempts = 3
        backoff = 1.0
        for i in range(attempts):
            try:
                return func(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504) and i < attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise RuntimeError(f"API request failed: {e}") from e
            except httpx.RequestError as e:
                if i < attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise RuntimeError(f"API request failed: {e}") from e

    return wrapper


class GeminiProvider(LLMProvider):
    """Gemini API provider implementation."""

    def __init__(self, api_key: str, default_model: str = "gemini-1.5-flash") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.client = httpx.Client(timeout=30.0)

    @_with_retries
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
        if model_name.startswith("models/"):
            model_name = model_name[7:]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        resp = self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini API returned no candidates: {data}")
        text_val = candidates[0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            content=str(text_val),
            prompt_tokens=int(usage.get("promptTokenCount", 0)),
            completion_tokens=int(usage.get("candidatesTokenCount", 0)),
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

    @_with_retries
    def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        model_name = model or "text-embedding-004"
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:embedContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"model": model_name, "content": {"parts": [{"text": text}]}}

        resp = self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        embedding = data["embedding"]["values"]
        return [float(x) for x in embedding]

    def count_tokens(self, text: str) -> int:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text, disallowed_special=()))
