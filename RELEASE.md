# Release Engineering & OSS Launch Guide

This document tracks the launch preparation for the first public Git release of Synapse (**v0.1.0**).

---

## 1. Release Notes: v0.1.0 (Beta)

We are proud to announce the first production-ready release of the **Synapse Temporal Cognitive Operating System**.

### Key Features
- **Git-Native Cognition**: Context objects and transaction journals addressed by content hashes and linked directly to your Git history.
- **Durable Event-Sourcing**: Journaled writes in SQLite WAL mode database backing transaction integrity.
- **Confidence & Drift Engine**: Time-decay algorithms, contradiction penalization, and git-diff source drift matching.
- **Visual Graph Projections**: Projection engine dynamically filters, caches, and clusters workspace topologies (Overview, Subsystem, Replay, Drift, Incidents).
- **Security-First Ingestion**: Escaping HTML payloads, blocklisting prompt injection patterns, and redacting secret keys/tokens from service responses.
- **Onboarding Experience**: Zero-config setup via `uv sync` and local visualizer.

---

## 2. OSS Launch Checklist

Before public GitHub publication:
- `[ ]` Create release tag: `git tag -a v0.1.0 -m "Release v0.1.0"`
- `[ ]` Push tag: `git push origin v0.1.0`
- `[ ]` Audit repository history for secrets using `gitleaks` or `trufflehog`.
- `[ ]` Confirm all unit tests pass on CI pipelines (GitHub Actions).
- `[ ]` Validate wheel compilation using `uv build`.
- `[ ]` Confirm `LICENSE.md` and `CODE_OF_CONDUCT.md` are present.

---

## 3. CLI & API Usage Examples

### CLI Command Reference
```bash
# Initialize state store
synapse init

# Check state
synapse status

# Record manual architectural decision note
synapse note "Use SQLite WAL mode for concurrency"

# Traverse history and print active timeline
synapse timeline

# Replay and verify state logs integrity
synapse lineage

# Deduplicate identical facts and migrate old states to cold database tables
synapse compact
```

### FastAPI Endpoint Reference
- `GET /api/v1/status`: Returns current daemon stats, active branch, and database counts.
- `GET /api/v1/timeline`: Lists temporal contexts and ancestry events.
- `GET /api/v1/projection/{context_hash}/{kind}`: Retrieves a ProjectionGraph. Can cluster automatically.
- `GET /api/v1/health`: Calculates Shannon change entropy and afferent/efferent coupling of packages.
- `POST /api/v1/compact`: Triggers compaction and returns migrated count.
- `POST /api/v1/note`: Accepts a JSON body containing a markdown note string, sanitizes it, and commits it.
