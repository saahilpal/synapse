from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

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
    """Get global Synap config file path (XDG-compliant)."""
    if env_path := os.environ.get("SYNAP_CONFIG"):
        return Path(env_path).expanduser()
    if os.environ.get("SYNAP_PROFILE", "").lower() == "test":
        return Path("/dev/null")
    return Path.home() / ".config" / "synap" / "config.toml"


class SynapSettings(BaseSettings):
    """Production-grade configuration with secure secret management."""

    model_config = SettingsConfigDict(
        env_prefix="SYNAP_",
        env_file=str(_get_config_file_path()),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    profile: RuntimeProfile = RuntimeProfile.DEV
    mode: RuntimeMode = RuntimeMode.ACTIVE

    repository_path: Path = Field(default=Path(), description="Repository root.")
    state_path: Path = Field(default=Path(".synap"), description="Local runtime state.")
    sqlite_path: Path | None = None
    log_path: Path | None = None

    logging_mode: LoggingMode = LoggingMode.HUMAN
    log_level: str = "INFO"

    max_file_bytes: int = Field(default=1_000_000, ge=1_024)

    checkpoint_threshold: float = 0.60
    lesson_expiry_days: int = 7

    llm_provider: str | None = Field(
        default=None,
        description="LLM provider (openai, gemini, ollama). Leave empty for Mode A (structural only).",
    )
    llm_model: str | None = Field(default=None, description="LLM model.")
    ollama_url: str = "http://127.0.0.1:11434"
    lm_studio_url: str = "http://127.0.0.1:1234"
    llama_cpp_url: str = "http://127.0.0.1:8080"
    vllm_url: str = "http://127.0.0.1:8000"
    jan_url: str = "http://127.0.0.1:1337"

    status_string: str = Field(
        default="Mode A (zero-LLM structural mode)",
        description="Runtime LLM provider status string.",
    )

    embedding_provider: str | None = Field(
        default=None,
        description="Embedding provider (e.g. openai, gemini, ollama). Defaults to llm_provider if not set.",
    )
    embedding_model: str | None = Field(default=None, description="Embedding model name.")
    embedding_url: str | None = Field(default=None, description="Custom URL for embedding API.")

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 9876

    daemon_poll_interval_seconds: float = 2.0
    shutdown_timeout_seconds: float = 5.0
    enable_file_wiki: bool = Field(
        default=False,
        description="Enable bulk LLM wiki generation for individual files (disabled by default to prevent token waste).",
    )

    def _get_fallback_credential(self, key: str) -> str | None:
        try:
            cred_file = Path.home() / ".synap" / "credentials"
            if cred_file.exists():
                import sys

                # Enforce chmod 600 on Unix-like systems
                if sys.platform != "win32":
                    import stat

                    mode = cred_file.stat().st_mode
                    if bool(mode & stat.S_IRGRP) or bool(mode & stat.S_IROTH):
                        return None

                for line in cred_file.read_text().splitlines():
                    if line.strip().startswith(f"{key}="):
                        return line.split("=", 1)[1].strip().strip("\"'")
        except Exception:
            import structlog

            structlog.get_logger(__name__).exception("fallback_credential_lookup_failed", key=key)
        return None

    @property
    def openai_api_key(self) -> str | None:
        return (
            keyring.get_password("synap", "openai_api_key")
            or os.environ.get("SYNAP_OPENAI_API_KEY")
            or self._get_fallback_credential("SYNAP_OPENAI_API_KEY")
        )

    @property
    def gemini_api_key(self) -> str | None:
        return (
            keyring.get_password("synap", "gemini_api_key")
            or os.environ.get("SYNAP_GEMINI_API_KEY")
            or self._get_fallback_credential("SYNAP_GEMINI_API_KEY")
        )

    @property
    def anthropic_api_key(self) -> str | None:
        return (
            keyring.get_password("synap", "anthropic_api_key")
            or os.environ.get("SYNAP_ANTHROPIC_API_KEY")
            or self._get_fallback_credential("SYNAP_ANTHROPIC_API_KEY")
        )

    @property
    def openrouter_api_key(self) -> str | None:
        return (
            keyring.get_password("synap", "openrouter_api_key")
            or os.environ.get("SYNAP_OPENROUTER_API_KEY")
            or self._get_fallback_credential("SYNAP_OPENROUTER_API_KEY")
        )

    @field_validator("repository_path", "state_path", mode="before")
    @classmethod
    def _expand_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @field_validator(
        "llm_provider", "embedding_provider", "llm_model", "embedding_model", mode="before"
    )
    @classmethod
    def _empty_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _derive_paths(self) -> Self:
        repository_path = self.repository_path.resolve()
        state_path = self.state_path
        if not state_path.is_absolute():
            state_path = repository_path / state_path
        self.repository_path = repository_path
        self.state_path = state_path.resolve()
        self.sqlite_path = self._resolve_optional_path(self.sqlite_path, "synap.db")
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

    def bind_discovered_runtime(self, force: bool = False) -> Any | None:
        """Probe for local LLM runtimes if llm_provider is not set.

        Binds to discovered runtime or enters Mode A.
        """
        if bool(self.llm_provider):
            return None

        from synap_git.provider.discovery import probe_local_runtimes

        cache_path = self.state_path / "provider_cache.json"
        discovered = probe_local_runtimes(cache_path=cache_path, force=force)
        if discovered is not None:
            self.llm_provider = discovered.name
            if not self.llm_model and discovered.chat_model:
                self.llm_model = discovered.chat_model
            if not self.embedding_provider and discovered.embedding_model:
                self.embedding_provider = discovered.name
                self.embedding_model = discovered.embedding_model
            if discovered.name == "ollama":
                self.ollama_url = discovered.host
            elif discovered.name == "lm_studio":
                self.lm_studio_url = discovered.host
            elif discovered.name == "llama_cpp":
                self.llama_cpp_url = discovered.host
            elif discovered.name == "vllm":
                self.vllm_url = discovered.host
            elif discovered.name == "jan":
                self.jan_url = discovered.host
            self.status_string = (
                f"Auto-discovered {discovered.name} (model: {discovered.chat_model or 'none'})"
            )
            return discovered
        else:
            self.status_string = "Mode A (zero-LLM structural mode)"
            return None

    def validate_configuration(self) -> list[str]:
        errors = []

        if self.llm_provider is None:
            self.bind_discovered_runtime()
            if self.llm_provider is None:
                self.status_string = "Mode A (zero-LLM structural mode)"
                return []

        provider_name = str(self.llm_provider).lower().strip()

        if provider_name == "openai" and not self.openai_api_key:
            errors.append("Missing OpenAI API key in keyring or SYNAP_OPENAI_API_KEY")
        if provider_name == "gemini" and not self.gemini_api_key:
            errors.append("Missing Gemini API key in keyring or SYNAP_GEMINI_API_KEY")
        if provider_name == "anthropic" and not self.anthropic_api_key:
            errors.append("Missing Anthropic API key in keyring or SYNAP_ANTHROPIC_API_KEY")
        if provider_name == "openrouter" and not self.openrouter_api_key:
            errors.append("Missing OpenRouter API key in keyring or SYNAP_OPENROUTER_API_KEY")

        from synap_git.provider.discovery import verify_model_exists

        model_err = verify_model_exists(self)
        if model_err:
            errors.append(model_err)

        return errors

    def test_connectivity(self) -> list[str]:
        errors = []
        if self.llm_provider is None:
            self.bind_discovered_runtime()
            if self.llm_provider is None:
                self.status_string = "Mode A (zero-LLM structural mode)"
                return []

        from synap_git.provider.factory import get_llm_provider

        try:
            get_llm_provider(self)
        except Exception as e:
            errors.append(f"Provider init failed: {e}")
            return errors

        from synap_git.provider.discovery import verify_provider_connectivity_and_model

        errors.extend(verify_provider_connectivity_and_model(self))
        return errors
