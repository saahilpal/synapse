from __future__ import annotations

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.provider.base import LLMProvider
from synapse.provider.gemini import GeminiProvider
from synapse.provider.mock import MockLLMProvider
from synapse.provider.ollama import OllamaProvider
from synapse.provider.openai import OpenAIProvider


def get_llm_provider(settings: SynapseSettings) -> LLMProvider:
    """Create an LLM provider based on runtime settings.

    In test profiles, or when required API keys are missing, it falls back
    to the MockLLMProvider.
    """
    if settings.profile == RuntimeProfile.TEST:
        return MockLLMProvider()

    provider_name = str(settings.llm_provider).lower().strip()

    if provider_name == "openai":
        if settings.openai_api_key:
            return OpenAIProvider(
                api_key=settings.openai_api_key,
                default_model=settings.llm_model,
            )
        # Fallback to mock if API key is not present (with warning)
        return MockLLMProvider()

    if provider_name == "gemini":
        if settings.gemini_api_key:
            return GeminiProvider(
                api_key=settings.gemini_api_key,
                default_model=settings.llm_model,
            )
        return MockLLMProvider()

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_url,
            default_model=settings.llm_model,
        )

    # Fallback/Default
    return MockLLMProvider()
