from __future__ import annotations

import json
import urllib.request
from typing import Any

from synapse.provider.base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """Ollama API provider implementation for local running models."""

    def __init__(
        self, base_url: str = "http://127.0.0.1:11434", default_model: str = "llama3"
    ) -> None:
        self.base_url = base_url.rstrip("/")
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
        url = f"{self.base_url}/api/chat"
        headers = {
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": temperature,
            },
            "stream": False,
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=300.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            message = data["message"]
            # Ollama provides prompt_eval_count and eval_count
            prompt_tokens = int(data.get("prompt_eval_count", 0))
            completion_tokens = int(data.get("eval_count", 0))
            return LLMResponse(
                content=str(message["content"]),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            raise RuntimeError(f"Ollama generate HTTP error {exc.code}: {err_body}") from exc
        except Exception as exc:
            raise RuntimeError(f"Ollama generate failed: {exc}") from exc

    def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        model_name = model or self.default_model
        url = f"{self.base_url}/api/embeddings"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {"model": model_name, "prompt": text}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            embedding = data["embedding"]
            return [float(x) for x in embedding]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            raise RuntimeError(f"Ollama embed HTTP error {exc.code}: {err_body}") from exc
        except Exception as exc:
            raise RuntimeError(f"Ollama embed failed: {exc}") from exc
