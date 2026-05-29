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


class OllamaProvider(LLMProvider):
    """Ollama API provider implementation for local running models."""

    def __init__(
        self, base_url: str = "http://127.0.0.1:11434", default_model: str = "llama3"
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.client = httpx.Client(timeout=300.0)

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
        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": temperature},
            "stream": False,
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        resp = self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        message = data["message"]
        prompt_tokens = int(data.get("prompt_eval_count", 0))
        completion_tokens = int(data.get("eval_count", 0))
        return LLMResponse(
            content=str(message["content"]),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
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
        model_name = model or self.default_model
        url = f"{self.base_url}/api/embeddings"
        headers = {"Content-Type": "application/json"}
        payload = {"model": model_name, "prompt": text}

        resp = self.client.post(url, json=payload, headers=headers, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        embedding = data["embedding"]
        return [float(x) for x in embedding]

    def count_tokens(self, text: str) -> int:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text, disallowed_special=()))
