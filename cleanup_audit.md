# Cleanup Audit

This audit records the final simplification pass that converges Synapse on persistent structural context infrastructure for AI coding agents.

## Keep

- `src/synapse/context/`: structural models, parser-backed extraction, Markdown semantic annotations, overlays, scanner, and context DAG.
- `src/synapse/storage/`: content-addressed object store and SQLite WAL context store.
- `src/synapse/transactions/`: journaled context commit boundary for atomic event/object/context writes.
- `src/synapse/replay/`: bounded diagnostic replay and integrity verification.
- `src/synapse/query/retrieval.py`: temporal filtering, structural traversal, semantic recall, and grounded LLM synthesis.
- `src/synapse/provider/`: small LLM provider abstraction for summaries, overlays, and embeddings.
- `src/synapse/runtime/`: local runtime service, daemon, queues, and snapshots.
- `src/synapse/api/`, `src/synapse/mcp/`, and `src/synapse/projections/`: agent/API/UI surfaces for grounded context access.

## Remove

- Speculative engines: assumptions, impact, incidents, lineage, health, drift, evolution, compaction, tiering, and advanced confidence subsystems.
- Duplicate replay facade under `src/synapse/runtime/replay.py`.
- Standalone temporal graph package.
- Legacy architecture, ADR, RFC, schema, security, runtime, storage, product, and evolution documentation trees.
- Root philosophy and launch documents (`VISION.md`, `ROADMAP.md`, `SKILLS.md`, `RELEASE.md`).
- Dead query model APIs and old projection modes for drift, assumptions, incidents, and branch-specific visualization.

## Merge

- Public terminology now uses context, structural nodes, semantic overlays, hybrid retrieval, and agent context APIs.
- The old internal package name was replaced by `src/synapse/context/`.
- The UI projection surface is reduced to overview, subsystem, history, and compare.

## Rewrite

- `ARCHITECTURE.md` is now the single canonical architecture document.
- `README.md`, `docs/quickstart.md`, `docs/ingestion.md`, `docs/retrieval.md`, `docs/overlays.md`, and `docs/troubleshooting.md` describe the actual product only.
- Structural extraction now creates graph nodes only for package, module/document, class, function, and import relationships.

## Postpone

- Dedicated vector database integration. Current retrieval uses provider embeddings with bounded in-process caching.
- Rich MCP server transport. The current facade preserves the tool boundary while runtime APIs stabilize.
- Advanced UI ergonomics beyond the working context explorer.
