# Synapse (`synap-git`)

> Fast, zero-cost, local Git-aware structural context and behavioral memory engine for AI coding agents.

[![CI Status](https://github.com/saahilpal/synapse/actions/workflows/ci.yml/badge.svg)](https://github.com/saahilpal/synapse/actions)
[![Version](https://img.shields.io/pypi/v/synap-git?color=3b82f6)](https://pypi.org/project/synap-git/)
[![Python Version](https://img.shields.io/pypi/pyversions/synap-git)](https://pypi.org/project/synap-git/)
[![License](https://img.shields.io/github/license/saahilpal/synapse?color=cbd5e1)](LICENSE.md)

---

## ⚡ 60-Second Developer Overview

AI coding agents burn thousands of tokens grepping full files and repeating reverted mistakes. **Synapse** is an offline-first AST code-graph and persistent memory engine that eliminates this waste:

1. **AST Skeletons (85.2% Token Reduction)**: Strips implementation bodies while keeping typed signatures and docstrings.
2. **Git Blast Radius**: Maps dirty lines to caller symbols and impacted test suites in milliseconds.
3. **Architectural Centrality**: Personalized PageRank discovers key hubs without full codebase dumps.
4. **Behavioral Memory & Lessons**: Retains working checkpoints, structural decisions, and negative constraints across agent turns.
5. **Zero Cloud, Zero Cost**: 100% local SQLite WAL storage; zero telemetry; zero external LLM API fees.

---

## 📊 Measured Benchmark Results

All metrics are benchmarked deterministically and match [`bench/numbers.json`](bench/numbers.json):

| Metric | Measured Value | Baseline / Comparison | Impact |
| :--- | :---: | :---: | :--- |
| **AST Skeleton Token Reduction** | **85.2%** | Full Raw Code | Strips bodies, preserves signatures/types |
| **Context Pack Token Footprint** | **833 tokens** | 58,400 tokens (Naive Read) | **85.7% overall token savings** |
| **Session Preamble Startup Tokens** | **712 tokens** | Budget: < 750 tokens | Active branch, dirty diff, hubs & lessons |
| **Incremental Reindexing (1 file change)** | **84 ms** | Full Reindex (1,800+ ms) | Git-hook triggered zero-daemon refresh |
| **Incremental Reindexing (0-change no-op)** | **14 ms** | Polling Loop (> 250 ms) | Sub-15ms cached verification |
| **P95 Symbol Lookup (`search`)** | **2.1 ms** | Ripgrep / FZF (~45 ms) | Sub-token split FTS5 index |
| **P95 Graph Neighborhood Traversal** | **0.8 ms** | Static Graph Parsers (~120 ms) | SQLite recursive CTE edge traversal |
| **P95 Preamble Generation** | **12.0 ms** | Cold Start (~350 ms) | Instant agent session startup |
| **Retrieval Recall@5 (Grounding)** | **63.33%** | 33.33% (Naive Lexical) | Hybrid RRF + PageRank ranking |
| **Retrieval Mean Reciprocal Rank (MRR)** | **0.4694** | 0.3778 (Unweighted) | High-precision top-rank matches |
| **Process Memory (RSS)** | **128 MB** | Target: < 200 MB | Lightweight local footprint |
| **SQLite Lock Timeout Errors** | **0 errors** | Multi-process contention | WAL mode with `synchronous=NORMAL` |

---

## 🚀 60-Second Quickstart

### 1. Install Synapse
```bash
pip install synap-git
```

### 2. Configure Your Environment & Auto-Detect Agents
```bash
synap install
```
This automatically:
- Indexes repository symbols via Tree-sitter AST parsers.
- Registers Synapse MCP servers for detected IDEs (Cursor, Claude Code, Windsurf, etc.).
- Installs zero-daemon Git hooks (`post-commit`, `post-checkout`) for sub-15ms auto-reindexing.
- Injects non-destructive directives into agent rule files.

### 3. Verify System & Inspect Context
```bash
# Print bounded startup context (< 750 tokens)
synap context

# Check system integrity and language grammars
synap doctor
```

---

## 🤖 Agent Compatibility Matrix

Synapse supports 10 major AI coding agents with non-destructive, idempotent sentinel injection (`<!-- SYNAP_MANAGED_START: v3.0 -->` ... `<!-- SYNAP_MANAGED_END -->`). Human instructions outside the sentinel are strictly preserved.

| AI Agent / Tool | Config / Directive Path | Status | Format |
| :--- | :--- | :---: | :--- |
| **Claude Code** | `.claude/skills/synap/SKILL.md`, `CLAUDE.md` | **tested end-to-end** | Skill + Markdown |
| **Cursor** | `.cursor/rules/synap.mdc` | **tested end-to-end** | MDC Rule |
| **Codex CLI** | `AGENTS.md` | **tested end-to-end** | Markdown |
| **Gemini CLI** | `AGENTS.md`, `.gemini/config/skills/synap/SKILL.md` | **tested end-to-end** | Markdown + Skill |
| **GitHub Copilot** | `.github/copilot-instructions.md` | **tested end-to-end** | Markdown |
| **Windsurf** | `.windsurfrules` | **tested end-to-end** | Markdown |
| **Cline / Roo Code** | `.clinerules` | **tested end-to-end** | Markdown |
| **Aider** | `.aider.conf.yml` | **generated, untested** | YAML |
| **Continue** | `.continue/config.json` | **generated, untested** | JSON |
| **Zed** | `.zed/settings.json` | **generated, untested** | JSON |

*For full details on agent detection and configuration, see [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).*

---

## 🌐 Repo-Local vs. Global Scope

Synapse cleanly separates repository-specific graph artifacts from user-wide global preferences:

### Repo-Local Scope (`.synap/` inside repository)
- **Database (`.synap/synap.db`)**: Local SQLite WAL database storing AST symbol hierarchies, import edges, file hashes, checkpoints, and negative lessons.
- **IPC & Locks (`.synap/daemon.pid`, `.synap/daemon.sock`)**: Local socket coordination for the background worker.
- **Git Hooks (`.git/hooks/post-commit`, `post-checkout`)**: Trigger instant local incremental indexing (< 85ms) without a continuous running daemon.
- **Safety**: Safe to commit `.synap/` configuration or add to `.gitignore` based on team policy.

### Global Scope (`~/.synap/` & User Home)
- **Global Config (`~/.synap/config.json`)**: User defaults (default profile, formatting preferences).
- **Secrets Store**: Uses OS-native System Keyring (macOS Keychain, Linux Secret Service, Windows Credential Manager).
- **Global IDE MCP Registration**: Configures user-level IDE files (e.g. `~/.cursor/mcp.json`, `~/.claude.json`, Claude Desktop) to connect to Synapse across all repositories.

---

## 🛠️ CLI Command Reference

### Exploration & Navigation
| Command | Shorthand | Description |
| :--- | :--- | :--- |
| `synap context` | `synap ctx` | Print token-bounded startup context pack (< 750 tokens). |
| `synap search <query>` | `synap search` | Hybrid AST symbol and lexical search with sub-token splitting. |
| `synap skeleton <file>` | `synap sk <file>` | Inspect structural AST skeleton (strips bodies, retains signatures). |
| `synap outline <file>` | `synap outline` | Map file structure, symbols, and line ranges. |
| `synap explain <symbol>`| `synap ex <sym>` | Deep structural symbol inspection (callers, callees, dependencies). |
| `synap hubs` | `synap hubs` | Discover top architectural hubs via PageRank centrality. |
| `synap pack` | `synap pack` | Export token-budgeted prompt pack with AST skeletons (< 8k tokens). |

### Git State & Blast Radius
| Command | Shorthand | Description |
| :--- | :--- | :--- |
| `synap blast` | `synap blast` | Check modified symbols, direct callers, and impacted tests. |
| `synap diff` | `synap diff` | View unified git diff of staged and dirty changes. |
| `synap test` | `synap t` | Execute only the test suites impacted by uncommitted git changes. |

### Memory & Behavioral Lessons
| Command | Description |
| :--- | :--- |
| `synap remember <key> <val>` | Store operational facts or environment requirements in persistent memory. |
| `synap recall <key>` | Retrieve operational facts from persistent memory. |
| `synap checkpoint create -m "..."` | Save current thought process and dirty working state before complex edits. |
| `synap checkpoint restore <id>` | Restore context state after agent turn completion or context compaction. |
| `synap lessons list` | Review active negative constraints and anti-regression rules. |

### System & Daemon Management
| Command | Description |
| :--- | :--- |
| `synap doctor` | Verify environment health, database integrity, and Tree-sitter parsers. |
| `synap repair` | Rebuild indexes, clean stale socket locks, and vacuum SQLite database. |
| `synap start` / `stop` / `status` | Manage optional background daemon process. |
| `synap ui` | Launch local web UI dashboard. |

---

## 🔧 Troubleshooting

### 1. `OperationalError: database is locked`
- **Cause:** Multiple concurrent processes attempting uncoordinated writes.
- **Resolution:** Synapse uses SQLite WAL mode with `PRAGMA synchronous = NORMAL` and exponential backoff retry loops. If an orphaned lock remains:
  ```bash
  synap repair
  ```

### 2. Tree-sitter Grammar Missing or Parsing Errors
- **Resolution:** Verify parser registration and compiler availability:
  ```bash
  synap doctor
  ```

### 3. Daemon Stalled or Port Conflict
- **Resolution:** Check daemon status and restart:
  ```bash
  synap status
  synap restart
  ```

---

## 🔒 Privacy & Security Guarantee

- **Zero Telemetry**: Synapse sends **zero bytes** across the network.
- **Zero Cloud Calls**: 100% of parsing, graph traversal, and memory indexing runs locally on your machine.
- **Zero External LLM Dependency**: Tree-sitter AST extraction, FTS5 lexical matching, and PageRank centrality require no API keys or third-party cloud services.
- **Secret Safety**: Secrets, tokens, API keys, passwords, and `.env` files are strictly filtered and never stored in the database.

---

## 📄 License

MIT © Saahil Pal
