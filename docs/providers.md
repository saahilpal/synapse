# LLM & Embedding Providers

Synap supports both local and cloud-hosted LLM and Vector Embedding providers. The system operates either in **Mode A** (pure structural AST graph, no LLM required) or **Mode B** (hybrid graph + semantic wiki + grounded search completions).

---

## Supported Generative LLM Providers

### 1. Ollama (Local First)
Runs completely offline on your workstation. No external API keys or network requests required.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "ollama"
  llm_model = "qwen2.5-coder:14b"
  ollama_url = "http://127.0.0.1:11434"
  ```
* **Recommended Models:** `qwen2.5-coder:14b`, `deepseek-coder-v2`, `llama3.3`.

### 2. OpenAI
Cloud model provider offering high reasoning capacity and code generation.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "openai"
  llm_model = "gpt-4o"
  ```
* **Recommended Models:** `gpt-4o`, `gpt-4o-mini`, `o3-mini`.

### 3. Google Gemini
Google DeepMind generative models.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "gemini"
  llm_model = "gemini-2.5-pro"
  ```
* **Recommended Models:** `gemini-2.5-pro`, `gemini-2.5-flash`.

### 4. Anthropic
Anthropic Claude models.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "anthropic"
  llm_model = "claude-3-5-sonnet-latest"
  ```
* **Recommended Models:** `claude-3-5-sonnet-latest`, `claude-3-5-haiku-latest`.

### 5. OpenRouter
Multi-model gateway routing to various open and proprietary providers with unified billing.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "openrouter"
  llm_model = "google/gemini-2.5-pro"
  ```

---

## Vector Embedding Providers

Synap provides vector embeddings for semantic search in hybrid retrieval. If `embedding_provider` is not explicitly declared, it inherits from `llm_provider`.

| Provider | Default Model | Configuration Keys |
| :--- | :--- | :--- |
| **OpenAI** | `text-embedding-3-small` | `embedding_provider = "openai"`<br>`embedding_model = "text-embedding-3-small"` |
| **Gemini** | `text-embedding-004` | `embedding_provider = "gemini"`<br>`embedding_model = "text-embedding-004"` |
| **Ollama** | `nomic-embed-text` | `embedding_provider = "ollama"`<br>`embedding_model = "nomic-embed-text"`<br>`embedding_url = "http://127.0.0.1:11434"` |
| **OpenRouter** | Configured model | `embedding_provider = "openrouter"`<br>`embedding_model = "<model-name>"` |

### Example Dual-Provider Configuration
You can configure different providers for generative tasks and embedding calculations:
```toml
# config.toml
[llm]
llm_provider = "anthropic"
llm_model = "claude-3-5-sonnet-latest"

[embeddings]
embedding_provider = "openai"
embedding_model = "text-embedding-3-small"
```

---

## Rate Limiting Architecture

Synap includes an internal `RateLimitedProvider` wrapper that:
* Enforces a ceiling of **15 calls per second** across background wiki tasks and query retrieval to prevent 429 HTTP errors and quota exhaustion.
* **Localhost Exemption:** When using local `OllamaProvider`, rate limiting is automatically bypassed so operations run at the maximum speed your local hardware permits.

---

## Secure Credential Storage

API keys can be configured via three mechanisms:

1. **Interactive Setup (Recommended):**
   ```bash
   synap setup .
   ```
   Saves credentials directly into the OS secure keyring.
2. **Environment Variables:**
   - `SYNAP_OPENAI_API_KEY`
   - `SYNAP_GEMINI_API_KEY`
   - `SYNAP_ANTHROPIC_API_KEY`
   - `SYNAP_OPENROUTER_API_KEY`
3. **Strict Fallback File:**
   - Saved at `~/.synap/credentials` with permissions restricted to `chmod 600`.
