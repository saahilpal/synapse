from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeProfile(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class RuntimeMode(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"
    INDEXING = "indexing"
    LOW_POWER = "low-power"


class LoggingMode(StrEnum):
    HUMAN = "human"
    JSON = "json"


class IndexingMode(StrEnum):
    FAST = "fast"
    FULL = "full"
    OFF = "off"


class SynapseSettings(BaseSettings):
    """Runtime configuration loaded from environment or defaults."""

    model_config = SettingsConfigDict(
        env_prefix="SYNAPSE_",
        env_nested_delimiter="__",
        env_file=str(Path("~/.synapse/.env").expanduser()),
        extra="ignore",
    )

    profile: RuntimeProfile = RuntimeProfile.DEV
    mode: RuntimeMode = RuntimeMode.ACTIVE

    repository_path: Path = Field(default=Path("."), description="Repository root.")
    state_path: Path = Field(default=Path(".synapse"), description="Local runtime state.")
    sqlite_path: Path | None = Field(default=None, description="SQLite DB path.")
    object_path: Path | None = Field(default=None, description="Object store path.")
    snapshot_path: Path | None = Field(default=None, description="Snapshot directory.")
    log_path: Path | None = Field(default=None, description="Local log directory.")

    logging_mode: LoggingMode = LoggingMode.HUMAN
    log_level: str = "INFO"
    correlation_id: str | None = None

    indexing_mode: IndexingMode = IndexingMode.FAST
    max_file_bytes: int = Field(default=1_000_000, ge=1_024)
    worker_concurrency: int = Field(default=2, ge=1, le=32)
    queue_max_size: int = Field(default=1_024, ge=1)
    retry_limit: int = Field(default=3, ge=0, le=20)
    low_power_mode: bool = Field(default=False, description="Defer expensive background work.")

    openai_api_key: str | None = Field(default=None, description="OpenAI API key.")
    gemini_api_key: str | None = Field(default=None, description="Gemini API key.")
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key.")
    ollama_url: str = Field(default="http://127.0.0.1:11434", description="Ollama API base URL.")
    llm_provider: str = Field(
        default="mock", description="Default LLM provider (openai, gemini, ollama, mock)."
    )
    llm_model: str = Field(default="mock-model", description="Default LLM model.")
    embed_provider: str | None = Field(
        default=None, description="Default embedding provider. Falls back to llm_provider."
    )
    embed_model: str | None = Field(default=None, description="Default embedding model.")

    mcp_enabled: bool = False
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8765, ge=1, le=65_535)

    daemon_poll_interval_seconds: float = Field(default=2.0, gt=0.0)

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
        self.snapshot_path = self._resolve_optional_path(self.snapshot_path, "snapshots")
        self.log_path = self._resolve_optional_path(self.log_path, "logs")
        if self.low_power_mode:
            self.mode = RuntimeMode.LOW_POWER
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
        assert self.object_path is not None
        assert self.snapshot_path is not None
        assert self.log_path is not None
        self.object_path.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.mkdir(parents=True, exist_ok=True)
        self.log_path.mkdir(parents=True, exist_ok=True)

    def inspect(self) -> dict[str, str | int | float | bool | None]:
        return {
            "profile": self.profile.value,
            "mode": self.mode.value,
            "repository_path": self.repository_path.as_posix(),
            "state_path": self.state_path.as_posix(),
            "sqlite_path": self.sqlite_path.as_posix() if self.sqlite_path else None,
            "object_path": self.object_path.as_posix() if self.object_path else None,
            "snapshot_path": self.snapshot_path.as_posix() if self.snapshot_path else None,
            "logging_mode": self.logging_mode.value,
            "log_level": self.log_level,
            "indexing_mode": self.indexing_mode.value,
            "worker_concurrency": self.worker_concurrency,
            "queue_max_size": self.queue_max_size,
            "mcp_enabled": self.mcp_enabled,
            "mcp_host": self.mcp_host,
            "mcp_port": self.mcp_port,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
        }
