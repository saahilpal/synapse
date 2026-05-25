<p align="center">
  <img src="assets/hero.svg" alt="Synapse" width="100%">
</p>

<p align="center">
  <b>Persistent structural context infrastructure for AI coding agents.</b>
</p>

<p align="center">
  <a href="https://github.com/synapse/synapse/actions"><img src="https://img.shields.io/github/actions/workflow/status/synapse/synapse/ci.yml?style=flat-square" alt="CI Status"></a>
  <a href="https://pypi.org/project/synapse-core/"><img src="https://img.shields.io/pypi/v/synapse-core?style=flat-square" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/synapse-core/"><img src="https://img.shields.io/pypi/pyversions/synapse-core?style=flat-square" alt="Python Versions"></a>
  <a href="LICENSE.md"><img src="https://img.shields.io/github/license/synapse/synapse?style=flat-square" alt="License"></a>
</p>

---

**Synapse** is a local-first service that indexes your repository, extracts its bounded structure (modules, classes, functions, imports), and stores versioned context. It exposes this structurally-grounded truth to AI agents via CLI, REST APIs, and the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

AI agents lose repository understanding over time. Token windows fill up with stale chats, and search relies on naive text embeddings. Synapse fixes this by giving agents **persistent, structurally-aware, and temporally-accurate** context retrieval.

## Why Synapse?

| Naive RAG / Embedding Search | Synapse Structural Context |
| :--- | :--- |
| Blind to module boundaries and file history. | Knows exactly where functions, classes, and modules begin and end. |
| Returns unstructured, disjointed text snippets. | Returns bounded structural subgraphs and deterministic lineage. |
| Overwrites context; loses the "why" behind changes. | Uses WAL-enabled SQLite + Object Store for temporal history and snapshots. |
| Slow, cloud-dependent. | Fast, local-first, runs entirely on your machine. |

## How it works

Synapse does **not** use AI to define structural truth. Parsers, Git state, content hashes, and SQLite transactions own the durable state. AI providers optionally summarize or explain the extracted context through non-destructive **semantic overlays**.

```mermaid
flowchart LR
    Repo[📁 Local Repo] -->|Ingest| Scanner(Scanner & Parser)
    Scanner -->|Delta| Store[(SQLite + Object Store)]
    Store -->|Temporal Filter| Retrieval[Hybrid Retrieval]
    Retrieval -->|MCP / API| Agent🤖
    
    style Repo fill:#1e293b,stroke:#3b82f6
    style Scanner fill:#1e293b,stroke:#8b5cf6
    style Store fill:#1e293b,stroke:#3b82f6
    style Retrieval fill:#1e293b,stroke:#8b5cf6
    style Agent fill:#1e293b,stroke:#3b82f6
```

## Installation

Synapse requires Python 3.10+ and is managed via `uv` for lightning-fast resolution.

```bash
uv tool install synapse-core
```

*(For development installation, see [Contributing](CONTRIBUTING.md).)*

## Quickstart

Initialize a Synapse index in your current repository:

```bash
synapse init .
```

Synapse immediately ingests the repository with deterministic exclusions and content hashes, building the initial structural graph.

Check the index status:

```bash
synapse status .
```

### Searching Structural Context

Agents and developers can search the structural index via the CLI. It uses a combination of structural traversal and semantic recall.

```bash
synapse search "auth module" .
synapse search "What changed in caching over time?" .
```

### Starting the Daemon & UI

To keep context continuously up-to-date and expose the API / MCP server:

```bash
# Starts the background scanner and API server
synapse start .

# Starts the Context UI (default port: 9876)
synapse ui . --host 127.0.0.1 --port 9876
```

## Agent Integration (MCP)

Synapse implements the **Model Context Protocol**, allowing seamless integration with tools like Claude Desktop, Cursor, or your own custom agents.

The Synapse MCP server exposes powerful tools:
- `get_current_context`: Retrieve the full structural boundaries of a target file.
- `get_context_diffs`: View the structural differences across temporal commits.
- `search_context`: Hybrid query across structural nodes and semantic overlays.
- `explain_structure`: Ask an LLM to synthesize a targeted answer using only grounded structural subgraphs.

## Documentation

Dive deeper into Synapse's architecture and advanced workflows:

- 🏗️ **[Architecture](ARCHITECTURE.md)**: Store internals, bounded replay, and object modeling.
- 🚀 **[Quickstart](docs/quickstart.md)**: Full guide to initialization and basic workflows.
- 🔄 **[Ingestion](docs/ingestion.md)**: How incremental scanning, deterministic exclusion, and invalidation work.
- 🧠 **[Retrieval](docs/retrieval.md)**: The four-stage hybrid retrieval pipeline.
- 🎨 **[Semantic Overlays](docs/overlays.md)**: AI-generated summaries attached to durable structure.

## Community & Contributing

We welcome contributions! Synapse is designed to be an infrastructure-grade project.
Please read our [Contributing Guide](CONTRIBUTING.md) to learn about our development workflow, testing standards, and PR process.

- Report a bug or request a feature: [GitHub Issues](https://github.com/synapse/synapse/issues)
- Read our [Code of Conduct](CODE_OF_CONDUCT.md)
- Security reporting: [Security Policy](SECURITY.md)

## License

Synapse is open-source software licensed under the [MIT License](LICENSE.md).
