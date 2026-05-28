# LLM Providers Configuration

Synap supports multiple local and cloud LLM providers. Provider configuration is set in the `config.toml` file under the `[llm]` section.

---

## Supported Providers

### 1. Ollama (Local First)
Runs models locally on your system. No API keys are required.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "ollama"
  llm_model = "qwen2.5-coder:14b"
  ollama_url = "http://localhost:11434"
  ```
* **Recommended Models:** `qwen2.5-coder:14b`, `deepseek-coder`, `llama3`.

### 2. OpenAI
Cloud model provider. Requires an API key.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "openai"
  llm_model = "gpt-4o"
  ```
* **Recommended Models:** `gpt-4o`, `gpt-4o-mini`, `o3-mini`.

### 3. Gemini
Google Cloud model provider. Requires an API key.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "gemini"
  llm_model = "gemini-2.5-pro"
  ```
* **Recommended Models:** `gemini-2.5-pro`, `gemini-2.5-flash`.

### 4. Anthropic
Anthropic cloud model provider. Requires an API key.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "anthropic"
  llm_model = "claude-3-5-sonnet-latest"
  ```
* **Recommended Models:** `claude-3-5-sonnet-latest`, `claude-3-5-haiku-latest`.

### 5. OpenRouter
Unified gateway routing to various open-source and commercial models. Requires an API key.
* **Configuration:**
  ```toml
  [llm]
  llm_provider = "openrouter"
  llm_model = "google/gemini-2.5-pro"
  ```

---

## API Key Configuration

Cloud providers require credentials. Synap searches for credentials using the following priority:

### Option A: System Keyring (Recommended)
API keys are stored securely in your OS keyring (Keychain on macOS, Secret Service on Linux, Credential Manager on Windows).
* Keys are automatically set when running `synap setup`.
* To check or verify keyring functionality, run:
  ```bash
  synap doctor
  ```

### Option B: Environment Variables
API keys can be defined as temporary session variables:
* OpenAI: `SYNAP_OPENAI_API_KEY`
* Gemini: `SYNAP_GEMINI_API_KEY`
* Anthropic: `SYNAP_ANTHROPIC_API_KEY`
* OpenRouter: `SYNAP_OPENROUTER_API_KEY`

### Option C: Fallback File
You can write credentials to `~/.synap/credentials` in the format:
```ini
SYNAP_OPENAI_API_KEY=your-api-key-here
```
* **Strict Security Rule:** On Unix systems, this file must have its permissions set to `600` (read/write access restricted solely to the owner). If the file is readable by group or others, the runtime will ignore it for security reasons.
