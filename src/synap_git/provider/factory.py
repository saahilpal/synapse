from __future__ import annotations

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.provider.anthropic import AnthropicProvider
from synap_git.provider.base import LLMProvider
from synap_git.provider.gemini import GeminiProvider
from synap_git.provider.mock import MockLLMProvider
from synap_git.provider.ollama import OllamaProvider
from synap_git.provider.openai import OpenAIProvider


def get_llm_provider(settings: SynapSettings) -> LLMProvider | None:
    """Create an LLM provider based on runtime settings.

    Strictly enforces provider configuration. Returns None for explicit Mode A
    (structural only). Mock provider is ONLY allowed during TEST profile.
    """
    if settings.profile == RuntimeProfile.TEST:
        return MockLLMProvider()

    if not settings.llm_provider:
        return None

    provider_name = str(settings.llm_provider).lower().strip()

    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API key missing. Set SYNAP_OPENAI_API_KEY or "
                "configure it in ~/.config/synap/config.toml"
            )
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            default_model=settings.llm_model or "",
        )

    if provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError(
                "Gemini API key missing. Set SYNAP_GEMINI_API_KEY or "
                "configure it in ~/.config/synap/config.toml"
            )
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            default_model=settings.llm_model or "",
        )

    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Anthropic API key missing. Set SYNAP_ANTHROPIC_API_KEY or "
                "configure it in ~/.config/synap/config.toml"
            )
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            default_model=settings.llm_model or "",
        )

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_url,
            default_model=settings.llm_model or "",
        )

    raise ValueError(f"Unsupported or unconfigured LLM provider: {provider_name}")


def get_embed_provider(settings: SynapSettings) -> LLMProvider | None:
    """Create an embedding provider based on runtime settings."""
    if settings.profile == RuntimeProfile.TEST:
        return MockLLMProvider()

    if not settings.llm_provider:
        return None

    provider_name = str(settings.llm_provider).lower().strip()
    model = settings.llm_model or ""

    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key missing for embeddings.")
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            default_model=model,
        )

    if provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("Gemini API key missing for embeddings.")
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            default_model=model,
        )

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_url,
            default_model=model,
        )

    raise ValueError(f"Unsupported or unconfigured embedding provider: {provider_name}")
