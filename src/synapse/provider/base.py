from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0


class LLMProvider(ABC):
    """Abstract interface for LLM provider clients."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Generate a response for the given prompts."""
        pass

    @abstractmethod
    def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        """Generate a vector embedding for the given text."""
        pass
