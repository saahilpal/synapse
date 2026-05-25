# Security Policy

Synapse handles repository context, architectural notes, and agent-facing memory. Treat it as sensitive local infrastructure.

## Supported Versions

The project is pre-release. Security fixes will target `main` until the first stable release policy is created.

## Security Principles

- Local-first by default.
- Explicit trust levels for all cognition sources.
- No silent promotion of untrusted agent output into durable truth.
- Permission-gated write operations through MCP and API surfaces.
- Provenance required for every durable fact.
- Derived indexes must be rebuildable and disposable.

## Reporting Vulnerabilities

Until a formal security contact exists, open a private maintainer channel or create a minimal public issue that does not disclose exploit details. Include the affected command, interface, or storage path and the expected trust boundary.

## Threat Classes

- Context poisoning through malicious docs, notes, or agent output.
- Tool poisoning through MCP descriptions or prompt injection.
- Unauthorized mutation of local cognition state.
- Exfiltration of repository-sensitive context.
- Cache tampering or replay corruption.
- Confused-deputy behavior across agents.

See the security subsystem docs under `docs/security/` for detailed controls.

