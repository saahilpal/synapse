from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Self

import keyring
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeProfile(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class RuntimeMode(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"


class LoggingMode(StrEnum):
    HUMAN = "human"
    JSON = "json"


def _get_config_file_path() -> Path:
    """Get global Synapse config file path (XDG-compliant)."""
    if env_path := os.environ.get("SYNAPSE_CONFIG"):
        return Path(env_path).expanduser()
    return Path.home() / ".config" / "synapse" / "config.toml"


class SynapseSettings(BaseSettings):
    """Production-grade configuration with secure secret management."""

    model_config = SettingsConfigDict(
        env_prefix="SYNAPSE_",
        env_file=str(_get_config_file_path()),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    profile: RuntimeProfile = RuntimeProfile.DEV
    mode: RuntimeMode = RuntimeMode.ACTIVE

    repository_path: Path = Field(default=Path(), description="Repository root.")
    state_path: Path = Field(default=Path(".synapse"), description="Local runtime state.")
    sqlite_path: Path | None = None
    object_path: Path | None = None
    log_path: Path | None = None

    logging_mode: LoggingMode = LoggingMode.HUMAN
    log_level: str = "INFO"

    max_file_bytes: int = Field(default=1_000_000, ge=1_024)

    llm_provider: str | None = Field(
        default=None,
        description="LLM provider (openai, gemini, ollama). Leave empty for Mode A (structural only).",
    )
    llm_model: str | None = Field(default=None, description="LLM model.")
    ollama_url: str = "http://127.0.0.1:11434"

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 9876

    daemon_poll_interval_seconds: float = 2.0

    @property
    def openai_api_key(self) -> str | None:
        return keyring.get_password("synapse", "openai_api_key") or os.environ.get(
            "SYNAPSE_OPENAI_API_KEY"
        )

    @property
    def gemini_api_key(self) -> str | None:
        return keyring.get_password("synapse", "gemini_api_key") or os.environ.get(
            "SYNAPSE_GEMINI_API_KEY"
        )

    @property
    def anthropic_api_key(self) -> str | None:
        return keyring.get_password("synapse", "anthropic_api_key") or os.environ.get(
            "SYNAPSE_ANTHROPIC_API_KEY"
        )

    @field_validator("repository_path", "state_path", mode="before")
    @classmethod
    def _expand_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @model_validator(mode="after")
    def _derive_paths(self) -> Self:
        repository_path = self.repository_path.resolve()
        state_path = self.state_path
        if not state_path.is_absolute():
            state_path = repository_path / state_path
        self.repository_path = repository_path
        self.state_path = state_path.resolve()
        self.sqlite_path = self._resolve_optional_path(self.sqlite_path, "synapse.db")
        self.object_path = self._resolve_optional_path(self.object_path, "objects")
        self.log_path = self._resolve_optional_path(self.log_path, "logs")

        if self.profile is RuntimeProfile.TEST:
            self.logging_mode = LoggingMode.JSON
            self.log_level = "DEBUG"
        return self

    def _resolve_optional_path(self, value: Path | None, default_name: str) -> Path:
        path = value or self.state_path / default_name
        if not path.is_absolute():
            path = self.repository_path / path
        return path.resolve()

    def ensure_directories(self) -> None:
        self.state_path.mkdir(parents=True, exist_ok=True)
        if self.object_path:
            self.object_path.mkdir(parents=True, exist_ok=True)
        if self.log_path:
            self.log_path.mkdir(parents=True, exist_ok=True)

    def validate_configuration(self) -> list[str]:
        errors = []

        if self.llm_provider == "openai" and not self.openai_api_key:
            errors.append("Missing OpenAI API key in keyring or SYNAPSE_OPENAI_API_KEY")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            errors.append("Missing Gemini API key in keyring or SYNAPSE_GEMINI_API_KEY")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            errors.append("Missing Anthropic API key in keyring or SYNAPSE_ANTHROPIC_API_KEY")

        return errors

    def test_connectivity(self) -> list[str]:
        errors = []
        from synapse.provider.factory import get_llm_provider

        try:
            get_llm_provider(self)
            if self.llm_provider == "ollama":
                import httpx

                resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=2.0)
                if resp.status_code != 200:
                    errors.append(f"Ollama offline: {resp.status_code}")
        except Exception as e:
            errors.append(f"Provider init failed: {e}")
        return errors
