# Troubleshooting

## `.synapse` State Was Not Created

Check write permission for the repository directory, then run:

```bash
uv run synapse init .
```

## SQLite Errors

Synapse uses a single local SQLite database in WAL mode. If `synapse.db` is corrupted, move `.synapse/synapse.db` aside and re-run initialization. Existing object-store data can still be checked with:

```bash
uv run synapse doctor .
```

## Parser Failures

Parser failures are captured as metadata and do not stop ingestion. Unsupported languages still produce file nodes, but not class/function/import nodes.

## Stale Overlays

If an overlay appears stale, re-run ingestion:

```bash
uv run synapse init . --force
```

Changed target files invalidate attached overlays in the next context commit.

## Large Repositories

Tune `SYNAPSE_MAX_FILE_BYTES`, keep generated folders excluded, and prefer task-specific retrieval queries. Retrieval has hard traversal and token bounds, so broad queries may return a representative context slice instead of every possible file.
