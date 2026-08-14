from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

from synap_git.config import SynapSettings
from synap_git.provider.anthropic import AnthropicProvider
from synap_git.provider.base import LLMProvider, LLMResponse
from synap_git.provider.gemini import GeminiProvider
from synap_git.provider.ollama import OllamaProvider
from synap_git.provider.openai import OpenAIProvider


class RateLimitedProvider(LLMProvider):
    def __init__(self, provider: LLMProvider, calls_per_second: float = 3.0):
        self._provider = provider
        self._min_interval = 1.0 / calls_per_second
        self._last_call = 0.0
        self._lock = threading.Lock()

    def _wait(self) -> None:
        with self._lock:
            now = time.time()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.time()

    def generate(self, *args: Any, **kwargs: Any) -> LLMResponse:
        self._wait()
        return self._provider.generate(*args, **kwargs)

    def generate_stream(self, *args: Any, **kwargs: Any) -> Iterator[str]:
        self._wait()
        return self._provider.generate_stream(*args, **kwargs)

    def embed(self, *args: Any, **kwargs: Any) -> list[float]:
        self._wait()
        return self._provider.embed(*args, **kwargs)

    def count_tokens(self, text: str) -> int:
        return self._provider.count_tokens(text)


def _wrap(provider: LLMProvider, calls_per_second: float | None = None) -> LLMProvider:
    if isinstance(provider, OllamaProvider):
        # Local Ollama provider running on localhost does not need artificial rate limiting
        return provider
    rate = calls_per_second if calls_per_second is not None else 15.0
    return RateLimitedProvider(provider, calls_per_second=rate)


def get_llm_provider(settings: SynapSettings) -> LLMProvider | None:
    """Create an LLM provider based on runtime settings.

    Strictly enforces provider configuration. Returns None for explicit Mode A
    (structural only).
    """
    if not settings.llm_provider:
        return None

    provider_name = str(settings.llm_provider).lower().strip()

    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API key missing. Set SYNAP_OPENAI_API_KEY or "
                "configure it in ~/.config/synap/config.toml"
            )
        return _wrap(
            OpenAIProvider(
                api_key=settings.openai_api_key,
                default_model=settings.llm_model or "",
            )
        )

    if provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError(
                "Gemini API key missing. Set SYNAP_GEMINI_API_KEY or "
                "configure it in ~/.config/synap/config.toml"
            )
        return _wrap(
            GeminiProvider(
                api_key=settings.gemini_api_key,
                default_model=settings.llm_model or "",
            )
        )

    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Anthropic API key missing. Set SYNAP_ANTHROPIC_API_KEY or "
                "configure it in ~/.config/synap/config.toml"
            )
        return _wrap(
            AnthropicProvider(
                api_key=settings.anthropic_api_key,
                default_model=settings.llm_model or "",
            )
        )

    if provider_name == "ollama":
        return _wrap(
            OllamaProvider(
                base_url=settings.ollama_url,
                default_model=settings.llm_model or "",
            )
        )

    if provider_name == "openrouter":
        if not settings.openrouter_api_key:
            raise ValueError(
                "OpenRouter API key missing. Set SYNAP_OPENROUTER_API_KEY or "
                "configure it in ~/.config/synap/config.toml"
            )
        from synap_git.provider.openrouter import OpenRouterProvider

        return _wrap(
            OpenRouterProvider(
                api_key=settings.openrouter_api_key,
                default_model=settings.llm_model or "",
            )
        )

    raise ValueError(f"Unsupported or unconfigured LLM provider: {provider_name}")


def get_embed_provider(settings: SynapSettings) -> LLMProvider | None:
    """Create an embedding provider based on runtime settings."""
    provider_val = settings.embedding_provider or settings.llm_provider
    if not provider_val:
        return None

    provider_name = str(provider_val).lower().strip()

    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key missing for embeddings.")
        return _wrap(
            OpenAIProvider(
                api_key=settings.openai_api_key,
                default_model=settings.embedding_model or "text-embedding-3-small",
            )
        )

    if provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("Gemini API key missing for embeddings.")
        return _wrap(
            GeminiProvider(
                api_key=settings.gemini_api_key,
                default_model=settings.embedding_model or "text-embedding-004",
            )
        )

    if provider_name == "ollama":
        base_url = settings.embedding_url or settings.ollama_url
        model = settings.embedding_model or "nomic-embed-text"
        return _wrap(
            OllamaProvider(
                base_url=base_url,
                default_model=model,
            )
        )

    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key missing for embeddings.")
        return _wrap(
            AnthropicProvider(
                api_key=settings.anthropic_api_key,
                default_model=settings.llm_model or "",
            )
        )

    if provider_name == "openrouter":
        if not settings.openrouter_api_key:
            raise ValueError("OpenRouter API key missing for embeddings.")
        from synap_git.provider.openrouter import OpenRouterProvider

        return _wrap(
            OpenRouterProvider(
                api_key=settings.openrouter_api_key,
                default_model=settings.llm_model or "",
            )
        )

    raise ValueError(f"Unsupported or unconfigured embedding provider: {provider_name}")
