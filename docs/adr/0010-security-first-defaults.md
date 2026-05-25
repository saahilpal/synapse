# ADR 0010: Security-First Defaults for Cognitive Exploration

## Context

Synapse parses raw repository contents, including code comments, markdown files, and config manifests. Treat all repository content as untrusted by default. Unsanitized display of these files exposes the user to XSS, path traversal attacks, and key leakage.

## Decision

We establish strict security boundaries at the API and rendering layers:
1. **Secret Redaction**: All API responses pass through a recursive `SecretRedactor` class that detects sensitive keys and redacts credentials (e.g. AWS secret, Slack token, GitHub token, base64 private key, database URI credentials) with `[REDACTED]`.
2. **Safe Markdown rendering**: Markdown content is converted using `markdown-it-py` with raw HTML elements disabled (`html=False`), escaping any raw tags. Link targets are validated to only use safe protocols (`http`, `https`, `file`, `git`), replacing unsafe protocols (like `javascript:`) with `#`.
3. **Input Validation**: All paths, limit integers, and payload sizes are validated to prevent directory traversal (`..` escapes) and Denial-of-Service attacks.
4. **Source Trust Classification**: A `TrustClassifier` validates source URIs against trust levels written in database trust records.

## Consequences

- Credentials inside files parsed by Synapse will never appear in UI panels, logs, or MCP tool outputs.
- Malicious repository files containing XSS payloads are safely rendered as plain text in the browser.
- File access is strictly locked to the workspace repository boundaries.
