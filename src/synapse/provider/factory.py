from __future__ import annotations

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.provider.anthropic import AnthropicProvider
from synapse.provider.base import LLMProvider
from synapse.provider.gemini import GeminiProvider
from synapse.provider.mock import MockLLMProvider
from synapse.provider.ollama import OllamaProvider
from synapse.provider.openai import OpenAIProvider


def get_llm_provider(settings: SynapseSettings) -> LLMProvider:
    """Create an LLM provider based on runtime settings."""
    if settings.profile == RuntimeProfile.TEST:
        return MockLLMProvider()

    provider_name = str(settings.llm_provider).lower().strip()

    if provider_name == "openai":
        if settings.openai_api_key:
            return OpenAIProvider(
                api_key=settings.openai_api_key,
                default_model=settings.llm_model,
            )
        return MockLLMProvider()

    if provider_name == "gemini":
        if settings.gemini_api_key:
            return GeminiProvider(
                api_key=settings.gemini_api_key,
                default_model=settings.llm_model,
            )
        return MockLLMProvider()

    if provider_name == "anthropic":
        if settings.anthropic_api_key:
            return AnthropicProvider(
                api_key=settings.anthropic_api_key,
                default_model=settings.llm_model,
            )
        return MockLLMProvider()

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_url,
            default_model=settings.llm_model,
        )

    return MockLLMProvider()


def get_embed_provider(settings: SynapseSettings) -> LLMProvider:
    """Create an embedding provider based on runtime settings."""
    if settings.profile == RuntimeProfile.TEST:
        return MockLLMProvider()

    provider_name = str(settings.embed_provider or settings.llm_provider).lower().strip()
    model = settings.embed_model or settings.llm_model

    if provider_name == "openai":
        if settings.openai_api_key:
            return OpenAIProvider(
                api_key=settings.openai_api_key,
                default_model=model,
            )
        return MockLLMProvider()

    if provider_name == "gemini":
        if settings.gemini_api_key:
            return GeminiProvider(
                api_key=settings.gemini_api_key,
                default_model=model,
            )
        return MockLLMProvider()

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_url,
            default_model=model,
        )

    return MockLLMProvider()
