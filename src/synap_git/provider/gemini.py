from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator
from typing import Any

from synap_git.provider.base import LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    """Gemini API provider implementation."""

    def __init__(self, api_key: str, default_model: str = "gemini-1.5-flash") -> None:
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
        # Strip models/ prefix if present
        if model_name.startswith("models/"):
            model_name = model_name[7:]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
            },
        }
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"Gemini API returned no candidates: {data}")
            text_val = candidates[0]["content"]["parts"][0]["text"]
            # Gemini does not always provide exact token counts in basic responses, or they might be in usageMetadata
            usage = data.get("usageMetadata", {})
            return LLMResponse(
                content=str(text_val),
                prompt_tokens=int(usage.get("promptTokenCount", 0)),
                completion_tokens=int(usage.get("candidatesTokenCount", 0)),
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini generate failed: {exc}") from exc

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
        model_name = model or "text-embedding-004"
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:embedContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {"model": model_name, "content": {"parts": [{"text": text}]}}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
            embedding = data["embedding"]["values"]
            return [float(x) for x in embedding]
        except Exception as exc:
            raise RuntimeError(f"Gemini embed failed: {exc}") from exc

    def count_tokens(self, text: str) -> int:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text, disallowed_special=()))
