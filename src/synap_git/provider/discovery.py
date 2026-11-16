from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from synap_git.config import SynapSettings

logger = structlog.get_logger(__name__)

CACHE_TTL_SECONDS = 3600.0  # 1 hour


@dataclass
class RuntimeTarget:
    name: str
    env_var: str
    default_port: int
    endpoint: str
    api_format: str
    priority: int


RUNTIME_TARGETS: list[RuntimeTarget] = [
    RuntimeTarget(
        name="ollama",
        env_var="OLLAMA_HOST",
        default_port=11434,
        endpoint="/api/tags",
        api_format="ollama",
        priority=5,
    ),
    RuntimeTarget(
        name="lm_studio",
        env_var="LM_STUDIO_HOST",
        default_port=1234,
        endpoint="/v1/models",
        api_format="openai_compatible",
        priority=4,
    ),
    RuntimeTarget(
        name="vllm",
        env_var="VLLM_HOST",
        default_port=8000,
        endpoint="/v1/models",
        api_format="openai_compatible",
        priority=3,
    ),
    RuntimeTarget(
        name="llama_cpp",
        env_var="LLAMA_CPP_HOST",
        default_port=8080,
        endpoint="/v1/models",
        api_format="openai_compatible",
        priority=2,
    ),
    RuntimeTarget(
        name="jan",
        env_var="JAN_HOST",
        default_port=1337,
        endpoint="/v1/models",
        api_format="openai_compatible",
        priority=1,
    ),
]


@dataclass
class DiscoveredRuntime:
    name: str
    host: str
    port: int
    models: list[str] = field(default_factory=list)
    chat_model: str | None = None
    embedding_model: str | None = None
    api_format: str = "openai_compatible"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveredRuntime:
        return cls(**data)


def normalize_host(host_str: str | None, default_port: int) -> tuple[str, int]:
    """Normalize environment host string or return default base URL and port."""
    if not host_str:
        return f"http://127.0.0.1:{default_port}", default_port
    raw = host_str.strip()
    if raw.startswith(":"):
        port = int(raw[1:])
        return f"http://127.0.0.1:{port}", port
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"http://{raw}"
    parsed = urllib.parse.urlparse(raw)
    port = parsed.port or default_port
    hostname = parsed.hostname or "127.0.0.1"
    if hostname == "0.0.0.0":  # nosec B104  # noqa: S104
        hostname = "127.0.0.1"
    scheme = parsed.scheme or "http"
    base_url = f"{scheme}://{hostname}:{port}"
    return base_url, port


_EMBEDDING_KEYWORDS = (
    "embed",
    "embedding",
    "nomic",
    "bge",
    "minilm",
    "gte",
    "e5",
    "arctic-embed",
    "sentence-transformers",
)


def is_embedding_model(model_name: str) -> bool:
    """Check if model appears to be an embedding model."""
    lower = model_name.lower()
    return any(kw in lower for kw in _EMBEDDING_KEYWORDS)


_PARAM_SIZE_REGEX = re.compile(r"(?:^|[_\-:])(\d+(?:\.\d+)?)b(?:[_\-:]|$)", re.IGNORECASE)


def extract_param_size_billion(model_name: str) -> float | None:
    """Extract model parameter size in billions from model name tag."""
    match = _PARAM_SIZE_REGEX.search(model_name)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def score_embedding_model(name: str) -> float:
    """Score embedding model for ranking (higher is better)."""
    lower = name.lower()
    score = 0.0

    if "bge-m3" in lower:
        score += 60.0
    elif "nomic-embed" in lower or "text-embedding-3" in lower or "bge-large" in lower:
        score += 50.0
    elif "snowflake-arctic" in lower or "gte-large" in lower or "e5-large" in lower:
        score += 45.0
    elif "bge-base" in lower or "gte-base" in lower or "e5-base" in lower:
        score += 40.0
    elif "minilm" in lower or "bge-small" in lower:
        score += 30.0
    elif "embed" in lower:
        score += 25.0
    else:
        score += 10.0

    if "latest" in lower:
        score += 2.0
    return score


def rank_embedding_models(models: list[str]) -> list[str]:
    """Rank embedding models in descending quality order."""
    embed_candidates = [m for m in models if is_embedding_model(m)]
    return sorted(embed_candidates, key=score_embedding_model, reverse=True)


def select_best_embedding_model(models: list[str]) -> str | None:
    """Select the best embedding model from a list of models."""
    ranked = rank_embedding_models(models)
    return ranked[0] if ranked else None


def score_chat_model(name: str) -> float:
    """Score chat model for code context generation (higher is better)."""
    lower = name.lower()
    score = 0.0

    # Code-specialized models are highest priority for Synapse
    if "qwen2.5-coder" in lower or "qwen-2.5-coder" in lower:
        score += 60.0
    elif "deepseek-coder" in lower:
        score += 55.0
    elif any(k in lower for k in ("starcoder", "codellama", "codegemma", "codestral")):
        score += 45.0
    elif "coder" in lower or "code" in lower:
        score += 35.0

    # High capability general foundation models
    if "llama3.3" in lower or "llama-3.3" in lower:
        score += 45.0
    elif "qwen2.5" in lower or "qwen-2.5" in lower:
        score += 42.0
    elif "deepseek-r1" in lower:
        score += 42.0
    elif "llama3.1" in lower or "llama-3.1" in lower:
        score += 40.0
    elif "phi4" in lower:
        score += 38.0
    elif "mistral" in lower or "mixtral" in lower:
        score += 35.0
    elif "llama3.2" in lower or "llama-3.2" in lower:
        score += 35.0
    elif "llama3" in lower or "llama-3" in lower:
        score += 30.0
    elif "gemma2" in lower:
        score += 28.0
    elif "phi3" in lower:
        score += 25.0
    elif "llama2" in lower:
        score += 10.0

    # Instruct / chat tuning bonus
    if "instruct" in lower or "chat" in lower:
        score += 15.0

    # Parameter size / speed balance
    size_b = extract_param_size_billion(lower)
    if size_b is not None:
        if 12.0 <= size_b <= 35.0:
            score += 30.0  # High reasoning, sweet spot
        elif 6.0 <= size_b <= 10.0:
            score += 25.0  # Fast and capable
        elif 30.0 < size_b <= 72.0:
            score += 20.0  # Very smart but memory/speed heavy
        elif 2.5 <= size_b < 6.0:
            score += 15.0  # Modest
        else:
            score += 5.0
    else:
        score += 15.0

    # Quantization bonus
    if any(q in lower for q in ("q4", "q5", "q8")):
        score += 5.0

    return score


def rank_chat_models(models: list[str]) -> list[str]:
    """Rank chat models in descending quality order."""
    chat_candidates = [m for m in models if not is_embedding_model(m)]
    if not chat_candidates and models:
        return []
    return sorted(chat_candidates, key=score_chat_model, reverse=True)


def select_best_chat_model(models: list[str]) -> str | None:
    """Select the best chat model from a list of models."""
    ranked = rank_chat_models(models)
    return ranked[0] if ranked else None


def model_matches(configured: str, available: list[str]) -> bool:
    """Fuzzy match configured model name against available model tags."""
    if not configured or not available:
        return False
    conf_norm = configured.strip().lower()
    for m in available:
        m_norm = m.strip().lower()
        if conf_norm == m_norm:
            return True
        if m_norm.endswith(":latest") and m_norm[:-7] == conf_norm:
            return True
        if conf_norm.endswith(":latest") and conf_norm[:-7] == m_norm:
            return True
        if ":" not in conf_norm and m_norm.split(":")[0] == conf_norm:
            return True
        if ":" not in m_norm and conf_norm.split(":")[0] == m_norm:
            return True
    return False


def extract_models(api_format: str, data: Any) -> list[str]:
    """Extract model identifiers from provider response JSON."""
    models: list[str] = []
    if api_format == "ollama":
        if isinstance(data, dict):
            raw_models = data.get("models", [])
            if isinstance(raw_models, list):
                for item in raw_models:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("model")
                        if name:
                            models.append(str(name))
                    elif isinstance(item, str):
                        models.append(item)
    else:  # openai_compatible
        items: list[Any] = []
        if isinstance(data, dict):
            items = data.get("data") or data.get("models") or []
        elif isinstance(data, list):
            items = data
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    mid = item.get("id") or item.get("name")
                    if mid:
                        models.append(str(mid))
                elif isinstance(item, str):
                    models.append(item)
    return models


def probe_single_target(target: RuntimeTarget, timeout: float = 0.5) -> DiscoveredRuntime | None:
    """Probe an individual runtime target with short timeout."""
    env_val = os.environ.get(target.env_var)
    base_url, port = normalize_host(env_val, target.default_port)
    probe_url = f"{base_url.rstrip('/')}{target.endpoint}"

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(probe_url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            models = extract_models(target.api_format, data)
            chat_model = select_best_chat_model(models)
            embedding_model = select_best_embedding_model(models)
            return DiscoveredRuntime(
                name=target.name,
                host=base_url,
                port=port,
                models=models,
                chat_model=chat_model,
                embedding_model=embedding_model,
                api_format=target.api_format,
            )
    except Exception:
        return None


def resolve_cache_file(cache_path: Path | str | None) -> Path:
    """Resolve provider cache file path."""
    if cache_path is None:
        return Path.cwd() / ".synap" / "provider_cache.json"
    p = Path(cache_path)
    if p.is_dir() or p.suffix != ".json":
        return p / "provider_cache.json"
    return p


def load_cached_runtime(
    cache_file: Path, ttl_seconds: float = CACHE_TTL_SECONDS
) -> DiscoveredRuntime | None:
    """Load cached runtime if valid and unexpired."""
    if not cache_file.exists():
        return None
    try:
        content = json.loads(cache_file.read_text(encoding="utf-8"))
        timestamp = float(content.get("timestamp", 0))
        if time.time() - timestamp > ttl_seconds:
            return None
        runtime_dict = content.get("runtime")
        if runtime_dict and isinstance(runtime_dict, dict):
            return DiscoveredRuntime.from_dict(runtime_dict)
    except Exception:
        return None
    return None


def save_cached_runtime(cache_file: Path, runtime: DiscoveredRuntime | None) -> None:
    """Save runtime to cache file with timestamp."""
    if runtime is None:
        return
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": time.time(),
            "runtime": runtime.to_dict(),
        }
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("save_cached_runtime_failed", error=str(exc))


def probe_local_runtimes(
    force: bool | Path | str = False,
    *,
    cache_path: Path | str | None = None,
) -> DiscoveredRuntime | None:
    """Discover running local LLM runtimes (Ollama, LM Studio, llama.cpp, vLLM, Jan).

    Probes default ports and env vars in parallel with 0.5s timeout.
    Results are cached in .synap/provider_cache.json for 1 hour.
    """
    is_force = False
    if isinstance(force, Path | str):
        cache_path = force
    elif isinstance(force, bool):
        is_force = force

    cache_file = resolve_cache_file(cache_path)

    if not is_force:
        cached = load_cached_runtime(cache_file)
        if cached is not None:
            return cached

    discovered_list: list[tuple[RuntimeTarget, DiscoveredRuntime]] = []
    with ThreadPoolExecutor(max_workers=len(RUNTIME_TARGETS)) as executor:
        futures = {
            executor.submit(probe_single_target, target, 0.5): target for target in RUNTIME_TARGETS
        }
        for future in as_completed(futures):
            target = futures[future]
            try:
                res = future.result()
                if res is not None:
                    discovered_list.append((target, res))
            except Exception as exc:
                logger.debug("probe_runtime_target_failed", target=target.name, error=str(exc))
                continue

    if not discovered_list:
        return None

    # Rank discovered runtimes:
    # 1. Has models available
    # 2. Priority score
    # 3. Model count
    discovered_list.sort(
        key=lambda item: (
            len(item[1].models) > 0,
            item[0].priority,
            len(item[1].models),
        ),
        reverse=True,
    )

    best_runtime = discovered_list[0][1]
    save_cached_runtime(cache_file, best_runtime)
    return best_runtime


def verify_provider_connectivity_and_model(settings: SynapSettings) -> list[str]:
    """Verify provider connectivity and ensure configured models actually exist."""
    errors: list[str] = []
    provider_name = str(settings.llm_provider).lower().strip() if settings.llm_provider else ""
    if not provider_name:
        return []

    if provider_name == "ollama":
        base_url = settings.ollama_url.rstrip("/")
        tags_url = f"{base_url}/api/tags"
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(tags_url)
                if resp.status_code != 200:
                    return [f"Ollama offline: HTTP {resp.status_code}"]
                data = resp.json()
                models = extract_models("ollama", data)
                if not models:
                    return [
                        "Ollama is running, but no models are installed. Run 'ollama pull <model>'"
                    ]
                if settings.llm_model and not model_matches(settings.llm_model, models):
                    errors.append(
                        f"Configured model '{settings.llm_model}' not found in Ollama models: {models}"
                    )
                if (
                    settings.embedding_provider == "ollama"
                    and settings.embedding_model
                    and not model_matches(settings.embedding_model, models)
                ):
                    errors.append(
                        f"Configured embedding model '{settings.embedding_model}' not found in Ollama models: {models}"
                    )
        except Exception as exc:
            return [f"Ollama offline: {exc}"]
        return errors

    if provider_name in ("lm_studio", "lmstudio", "llama_cpp", "llamacpp", "vllm", "jan"):
        url_map = {
            "lm_studio": getattr(settings, "lm_studio_url", "http://127.0.0.1:1234"),
            "lmstudio": getattr(settings, "lm_studio_url", "http://127.0.0.1:1234"),
            "llama_cpp": getattr(settings, "llama_cpp_url", "http://127.0.0.1:8080"),
            "llamacpp": getattr(settings, "llama_cpp_url", "http://127.0.0.1:8080"),
            "vllm": getattr(settings, "vllm_url", "http://127.0.0.1:8000"),
            "jan": getattr(settings, "jan_url", "http://127.0.0.1:1337"),
        }
        base = url_map.get(provider_name, "http://127.0.0.1:1234")
        models_url = f"{base.rstrip('/')}/v1/models"
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(models_url)
                if resp.status_code != 200:
                    return [f"{provider_name} offline: HTTP {resp.status_code}"]
                data = resp.json()
                models = extract_models("openai_compatible", data)
                if not models:
                    return [f"{provider_name} is running, but no models are loaded"]
                if settings.llm_model and not model_matches(settings.llm_model, models):
                    errors.append(
                        f"Configured model '{settings.llm_model}' not found on {provider_name}: {models}"
                    )
                if (
                    settings.embedding_provider in url_map
                    and settings.embedding_model
                    and not model_matches(settings.embedding_model, models)
                ):
                    errors.append(
                        f"Configured embedding model '{settings.embedding_model}' not found on {provider_name}: {models}"
                    )
        except Exception as exc:
            return [f"{provider_name} offline: {exc}"]
        return errors

    return errors


def verify_model_exists(settings: SynapSettings) -> str | None:
    """Verify configured model exists on reachable provider, or return error string."""
    errs = verify_provider_connectivity_and_model(settings)
    return errs[0] if errs else None
