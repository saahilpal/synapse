# Troubleshooting

## Installation Issues

### Tree-sitter build errors
Synap uses pre-compiled grammars via `tree-sitter-languages`. If you encounter build errors, ensure you have a modern C compiler installed (`gcc` or `clang`).

### Missing `tiktoken` cache
On some air-gapped systems, `tiktoken` may fail to download its vocabulary. Set the `TIKTOKEN_CACHE_DIR` environment variable to a pre-populated directory.

## Configuration Issues

### Provider connection failed
Run `synap doctor` to verify connectivity.
- **Ollama:** Ensure the service is running (`ollama serve`) and accessible at the configured URL.
- **OpenAI/Anthropic:** Verify that your API keys are correctly set in the system keyring or environment variables.

## Retrieval Issues

### Hallucinations
If the agent is hallucinating code that doesn't exist:
1. Check the **Diagnostic Trace** to see what context Synap provided.
2. Ensure you have run `synap init` or that the daemon is running to capture recent changes.

### No results found
If `synap search` returns no results:
1. Verify that the file types are supported (Python, JS, TS).
2. Check if the files are excluded by `.gitignore` or the `max_file_bytes` limit.
