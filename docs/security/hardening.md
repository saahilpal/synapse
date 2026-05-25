# Security Hardening Policy

Synapse enforces strict boundaries when parsing and displaying repository data:

## 1. Secret Detection & Redaction
The `SecretRedactor` scans all dictionaries, lists, and strings returned by API endpoints.
- **Keys**: Keys containing substring `password`, `secret`, `token`, `key`, `credential`, `jwt`, `auth` are replaced with `[REDACTED]`.
- **Regex Patterns**: String values are scanned for signatures matching:
  - AWS credentials (`AKIA...`)
  - GitHub tokens (`ghp_...`, `github_pat_...`)
  - Slack API tokens (`xoxb-...`)
  - SSH private key headers (`-----BEGIN ... PRIVATE KEY-----`)
  - Database URL credentials (`postgresql://user:password@host`)

## 2. Safe Markdown Render
Markdown documents from the codebase are rendered securely:
- Raw HTML is disabled by setting `html=False` in `markdown-it-py`. All raw tags are escaped as text.
- Anchors and images must use safe protocols: `http`, `https`, `file`, or `git`. Unsafe links (e.g., `javascript:`) are rewritten to `#`.

## 3. Path Traversal Protection
All path parameters passed to the API are parsed relative to the repository root. If the resolved path traverses outside the repository boundaries (using relative `..` components or absolute roots), a `ValueError` is raised, returning an HTTP 400 bad request.
