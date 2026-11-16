from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.provider.discovery import (
    DiscoveredRuntime,
    extract_models,
    extract_param_size_billion,
    is_embedding_model,
    load_cached_runtime,
    model_matches,
    normalize_host,
    probe_local_runtimes,
    rank_chat_models,
    rank_embedding_models,
    save_cached_runtime,
    select_best_chat_model,
    select_best_embedding_model,
    verify_provider_connectivity_and_model,
)
from synap_git.provider.factory import get_embed_provider, get_llm_provider
from synap_git.provider.ollama import OllamaProvider
from synap_git.provider.openai import OpenAIProvider


@pytest.fixture(autouse=True)
def isolate_synap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAP_LLM_PROVIDER", "")
    monkeypatch.setenv("SYNAP_LLM_MODEL", "")
    monkeypatch.setenv("SYNAP_EMBEDDING_PROVIDER", "")
    monkeypatch.setenv("SYNAP_EMBEDDING_MODEL", "")


def test_normalize_host() -> None:
    # Default fallback
    assert normalize_host(None, 11434) == ("http://127.0.0.1:11434", 11434)
    assert normalize_host("", 1234) == ("http://127.0.0.1:1234", 1234)

    # Port prefix only
    assert normalize_host(":8080", 8080) == ("http://127.0.0.1:8080", 8080)

    # Host without scheme
    assert normalize_host("localhost:11434", 11434) == ("http://localhost:11434", 11434)
    assert normalize_host("127.0.0.1:9000", 11434) == ("http://127.0.0.1:9000", 9000)

    # Scheme present
    assert normalize_host("http://myhost:1234", 1234) == ("http://myhost:1234", 1234)
    assert normalize_host("https://secure.local:8443", 8443) == ("https://secure.local:8443", 8443)

    # 0.0.0.0 normalized to 127.0.0.1 for client requests
    assert normalize_host("0.0.0.0:8000", 8000) == ("http://127.0.0.1:8000", 8000)


def test_model_type_and_param_extraction() -> None:
    # Embedding keyword detection
    assert is_embedding_model("nomic-embed-text:latest") is True
    assert is_embedding_model("bge-m3:latest") is True
    assert is_embedding_model("text-embedding-3-small") is True
    assert is_embedding_model("all-minilm-l6-v2") is True
    assert is_embedding_model("snowflake-arctic-embed") is True
    assert is_embedding_model("qwen2.5-coder:7b") is False
    assert is_embedding_model("llama3.1:8b") is False

    # Parameter size extraction
    assert extract_param_size_billion("llama3.1:8b") == 8.0
    assert extract_param_size_billion("qwen2.5-coder:14b-instruct-q4_K_M") == 14.0
    assert extract_param_size_billion("deepseek-coder:6.7b") == 6.7
    assert extract_param_size_billion("phi-3-mini-3.8b") == 3.8
    assert extract_param_size_billion("custom-model-no-size") is None


def test_model_ranking_and_selection() -> None:
    models = [
        "llama3.1:8b",
        "nomic-embed-text:latest",
        "qwen2.5-coder:7b",
        "mistral:7b",
        "bge-m3:latest",
    ]

    # Best chat model should prioritize coder models
    best_chat = select_best_chat_model(models)
    assert best_chat == "qwen2.5-coder:7b"

    # Chat ranking should exclude embedding models
    ranked_chat = rank_chat_models(models)
    assert "nomic-embed-text:latest" not in ranked_chat
    assert "bge-m3:latest" not in ranked_chat
    assert ranked_chat[0] == "qwen2.5-coder:7b"
    assert ranked_chat[1] == "llama3.1:8b"

    # Embedding selection
    best_embed = select_best_embedding_model(models)
    assert best_embed == "bge-m3:latest"

    ranked_embed = rank_embedding_models(models)
    assert ranked_embed[0] == "bge-m3:latest"
    assert ranked_embed[1] == "nomic-embed-text:latest"
    assert "llama3.1:8b" not in ranked_embed

    # Empty / non-matching list
    assert select_best_chat_model([]) is None
    assert select_best_embedding_model([]) is None
    assert select_best_embedding_model(["llama3.1:8b"]) is None


def test_model_matches() -> None:
    available = ["llama3.1:8b", "nomic-embed-text:latest", "qwen2.5-coder:7b"]

    assert model_matches("llama3.1:8b", available) is True
    assert model_matches("llama3.1", available) is True
    assert model_matches("nomic-embed-text", available) is True
    assert model_matches("nomic-embed-text:latest", available) is True
    assert model_matches("qwen2.5-coder", available) is True
    assert model_matches("gpt-4o", available) is False
    assert model_matches("", available) is False
    assert model_matches("llama3", []) is False


def test_extract_models() -> None:
    # Ollama response
    ollama_data = {
        "models": [
            {"name": "llama3.1:8b", "size": 4000000},
            {"model": "nomic-embed-text:latest"},
            "raw-string-model",
        ]
    }
    extracted_ollama = extract_models("ollama", ollama_data)
    assert extracted_ollama == ["llama3.1:8b", "nomic-embed-text:latest", "raw-string-model"]

    # OpenAI-compatible response
    openai_data = {
        "data": [
            {"id": "qwen2.5-coder-7b"},
            {"id": "bge-m3"},
        ]
    }
    extracted_openai = extract_models("openai_compatible", openai_data)
    assert extracted_openai == ["qwen2.5-coder-7b", "bge-m3"]

    # Malformed data
    assert extract_models("ollama", {}) == []
    assert extract_models("openai_compatible", {}) == []
    assert extract_models("openai_compatible", "invalid") == []


def test_cache_lifecycle(tmp_path: Path) -> None:
    cache_file = tmp_path / "provider_cache.json"

    # Non-existent cache
    assert load_cached_runtime(cache_file) is None

    runtime = DiscoveredRuntime(
        name="ollama",
        host="http://127.0.0.1:11434",
        port=11434,
        models=["llama3.1:8b", "nomic-embed-text:latest"],
        chat_model="llama3.1:8b",
        embedding_model="nomic-embed-text:latest",
        api_format="ollama",
    )

    # Save to cache
    save_cached_runtime(cache_file, runtime)
    assert cache_file.exists()

    # Load from cache (fresh)
    loaded = load_cached_runtime(cache_file, ttl_seconds=3600.0)
    assert loaded is not None
    assert loaded.name == "ollama"
    assert loaded.chat_model == "llama3.1:8b"
    assert loaded.embedding_model == "nomic-embed-text:latest"

    # Expired cache
    loaded_expired = load_cached_runtime(cache_file, ttl_seconds=-1.0)
    assert loaded_expired is None

    # Corrupted cache
    cache_file.write_text("invalid json", encoding="utf-8")
    assert load_cached_runtime(cache_file) is None


def test_probe_local_runtimes_ollama_discovered(tmp_path: Path) -> None:
    cache_path = tmp_path / "provider_cache.json"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5-coder:7b"},
            {"name": "nomic-embed-text:latest"},
        ]
    }

    def fake_get(url: str, **kwargs: Any) -> Any:
        if "11434/api/tags" in url:
            return mock_resp
        raise ConnectionRefusedError("Offline")

    with patch("httpx.Client.get", side_effect=fake_get):
        runtime = probe_local_runtimes(force=True, cache_path=cache_path)

    assert runtime is not None
    assert runtime.name == "ollama"
    assert runtime.port == 11434
    assert runtime.chat_model == "qwen2.5-coder:7b"
    assert runtime.embedding_model == "nomic-embed-text:latest"
    assert cache_path.exists()

    # Second call should use cache without probing
    with patch("httpx.Client.get", side_effect=RuntimeError("Should not be called")):
        cached_runtime = probe_local_runtimes(force=False, cache_path=cache_path)
    assert cached_runtime is not None
    assert cached_runtime.name == "ollama"


def test_probe_local_runtimes_lm_studio_discovered(tmp_path: Path) -> None:
    cache_path = tmp_path / "provider_cache.json"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "qwen2.5-coder-7b-instruct"},
            {"id": "bge-m3"},
        ]
    }

    def fake_get(url: str, **kwargs: Any) -> Any:
        if "1234/v1/models" in url:
            return mock_resp
        raise ConnectionRefusedError("Offline")

    with patch("httpx.Client.get", side_effect=fake_get):
        runtime = probe_local_runtimes(force=True, cache_path=cache_path)

    assert runtime is not None
    assert runtime.name == "lm_studio"
    assert runtime.port == 1234
    assert runtime.chat_model == "qwen2.5-coder-7b-instruct"
    assert runtime.embedding_model == "bge-m3"


def test_probe_local_runtimes_all_offline(tmp_path: Path) -> None:
    cache_path = tmp_path / "provider_cache.json"

    with patch("httpx.Client.get", side_effect=ConnectionRefusedError("Offline")):
        runtime = probe_local_runtimes(force=True, cache_path=cache_path)

    assert runtime is None
    # Ensure failure is not cached as an active runtime
    assert not cache_path.exists()


def test_probe_local_runtimes_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "provider_cache.json"
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:19999")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}]}

    requested_urls: list[str] = []

    def fake_get(url: str, **kwargs: Any) -> Any:
        requested_urls.append(url)
        if "19999/api/tags" in url:
            return mock_resp
        raise ConnectionRefusedError("Offline")

    with patch("httpx.Client.get", side_effect=fake_get):
        runtime = probe_local_runtimes(force=True, cache_path=cache_path)

    assert runtime is not None
    assert runtime.name == "ollama"
    assert runtime.port == 19999
    assert any("19999/api/tags" in u for u in requested_urls)


def test_factory_dynamic_binding_ollama(tmp_path: Path) -> None:
    cache_path = tmp_path / ".synap" / "provider_cache.json"
    cached = DiscoveredRuntime(
        name="ollama",
        host="http://127.0.0.1:11434",
        port=11434,
        models=["qwen2.5-coder:7b", "nomic-embed-text:latest"],
        chat_model="qwen2.5-coder:7b",
        embedding_model="nomic-embed-text:latest",
        api_format="ollama",
    )
    save_cached_runtime(cache_path, cached)

    settings = SynapSettings(repository_path=tmp_path, profile=RuntimeProfile.TEST)
    assert settings.llm_provider is None

    provider = get_llm_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.default_model == "qwen2.5-coder:7b"
    assert provider.base_url == "http://127.0.0.1:11434"

    embed_provider = get_embed_provider(settings)
    assert isinstance(embed_provider, OllamaProvider)
    assert embed_provider.default_model == "nomic-embed-text:latest"


def test_factory_dynamic_binding_lm_studio(tmp_path: Path) -> None:
    cache_path = tmp_path / ".synap" / "provider_cache.json"
    cached = DiscoveredRuntime(
        name="lm_studio",
        host="http://127.0.0.1:1234",
        port=1234,
        models=["qwen2.5-coder-7b-instruct", "bge-m3"],
        chat_model="qwen2.5-coder-7b-instruct",
        embedding_model="bge-m3",
        api_format="openai_compatible",
    )
    save_cached_runtime(cache_path, cached)

    settings = SynapSettings(repository_path=tmp_path, profile=RuntimeProfile.TEST)
    assert settings.llm_provider is None

    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert provider.default_model == "qwen2.5-coder-7b-instruct"
    assert provider.base_url == "http://127.0.0.1:1234/v1"

    embed_provider = get_embed_provider(settings)
    assert isinstance(embed_provider, OpenAIProvider)
    assert embed_provider.default_model == "bge-m3"


def test_factory_mode_a_when_nothing_discovered(tmp_path: Path) -> None:
    settings = SynapSettings(repository_path=tmp_path, profile=RuntimeProfile.TEST)

    with patch("httpx.Client.get", side_effect=ConnectionRefusedError("Offline")):
        provider = get_llm_provider(settings)
        embed_provider = get_embed_provider(settings)

    assert provider is None
    assert embed_provider is None


def test_config_bind_and_model_verification(tmp_path: Path) -> None:
    settings = SynapSettings(repository_path=tmp_path, profile=RuntimeProfile.TEST)
    assert settings.status_string == "Mode A (zero-LLM structural mode)"

    # Mode A validation with nothing running
    with patch("httpx.Client.get", side_effect=ConnectionRefusedError("Offline")):
        val_errors = settings.validate_configuration()
        conn_errors = settings.test_connectivity()

    assert val_errors == []
    assert conn_errors == []
    assert settings.status_string == "Mode A (zero-LLM structural mode)"

    # Now simulate Ollama with models
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [
            {"name": "llama3.1:8b"},
            {"name": "nomic-embed-text:latest"},
        ]
    }

    # Bind discovered runtime
    with patch("httpx.Client.get", return_value=mock_resp):
        discovered = settings.bind_discovered_runtime(force=True)

    assert discovered is not None
    assert settings.llm_provider == "ollama"
    assert settings.llm_model == "llama3.1:8b"
    assert settings.embedding_model == "nomic-embed-text:latest"
    assert "Auto-discovered ollama" in settings.status_string

    # Verify model existence succeeds when model is present
    with patch("httpx.Client.get", return_value=mock_resp):
        val_errors = settings.validate_configuration()
        conn_errors = settings.test_connectivity()
    assert val_errors == []
    assert conn_errors == []

    # Verify model existence fails when configured model does not exist
    settings.llm_model = "non-existent-model"
    with patch("httpx.Client.get", return_value=mock_resp):
        conn_errors = settings.test_connectivity()
    assert len(conn_errors) == 1
    assert "non-existent-model" in conn_errors[0]
    assert "not found in Ollama models" in conn_errors[0]

    # Verify model existence fails when Ollama has no models installed
    empty_resp = MagicMock()
    empty_resp.status_code = 200
    empty_resp.json.return_value = {"models": []}
    with patch("httpx.Client.get", return_value=empty_resp):
        conn_errors = settings.test_connectivity()
    assert len(conn_errors) == 1
    assert "no models are installed" in conn_errors[0]


def test_verify_provider_connectivity_openai_compatible(tmp_path: Path) -> None:
    settings = SynapSettings(
        repository_path=tmp_path,
        llm_provider="lm_studio",
        llm_model="qwen2.5-coder-7b",
        profile=RuntimeProfile.TEST,
    )

    # Provider offline
    with patch("httpx.Client.get", side_effect=ConnectionRefusedError("Offline")):
        errs = verify_provider_connectivity_and_model(settings)
    assert len(errs) == 1
    assert "lm_studio offline" in errs[0]

    # Provider online, model exists
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "qwen2.5-coder-7b"}]}
    with patch("httpx.Client.get", return_value=mock_resp):
        errs = verify_provider_connectivity_and_model(settings)
    assert errs == []

    # Provider online, model missing
    mock_resp.json.return_value = {"data": [{"id": "different-model"}]}
    with patch("httpx.Client.get", return_value=mock_resp):
        errs = verify_provider_connectivity_and_model(settings)
    assert len(errs) == 1
    assert "not found on lm_studio" in errs[0]
