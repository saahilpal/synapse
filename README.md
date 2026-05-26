# Synapse 🧠

<p align="center">
  <img src="assets/hero.svg" alt="Synapse Hero" width="800">
</p>

<p align="center">
  <b>The Deterministic Context Injector for AI Coding Agents.</b>
</p>

<p align="center">
  <a href="https://github.com/saahilpal/synapse/actions"><img src="https://img.shields.io/github/actions/workflow/status/saahilpal/synapse/ci.yml?style=flat-square&color=3b82f6" alt="CI Status"></a>
  <a href="LICENSE.md"><img src="https://img.shields.io/github/license/saahilpal/synapse?style=flat-square&color=cbd5e1" alt="License"></a>
  <a href="SYNAPSE_BUILD_SPEC.md"><img src="https://img.shields.io/badge/spec-v1.0-green?style=flat-square" alt="Spec Compliant"></a>
  <img src="https://img.shields.io/badge/architecture-deterministic-orange?style=flat-square" alt="Deterministic">
</p>

---

### 🛑 Stop using RAG for code.

Synapse is **NOT a RAG system.** It is a strict, deterministic background daemon that mirrors your Git state and proactively pushes exact contextual boundaries to AI coding agents via the Model Context Protocol (MCP).

**Agents do not query Synapse—Synapse *injects* reality into Agents.**

---

## 💡 Why Synapse?

<p align="center">
  <img src="assets/why-synapse.svg" alt="Why Synapse" width="600">
</p>

| Feature | Legacy RAG / Vector Search | Synapse (Deterministic Injection) |
| :--- | :--- | :--- |
| **Accuracy** | Probabilistic (can hallucinate context) | **100% Deterministic (Git-linked)** |
| **Discovery** | "Pull" (Agent must know what to ask) | **"Push" (Synapse bounds the session)** |
| **State** | Ignores Git branch/commit state | **Perfectly synced with `HEAD`** |
| **Memory** | Short-term or noisy | **Structured Behavioral Memory (L3)** |
| **Privacy** | Often sends chunks to cloud | **100% Local-First** |

---

## 🏛️ Core Pillars

1.  **DETERMINISTIC FIRST:** If the agent sees it, it exists exactly as shown in the local filesystem.
2.  **PUSH, NOT PULL:** Agents are terrible at querying for what they don't know exists. Synapse bounds their context upfront.
3.  **NOTHING HAPPENS SILENTLY:** Every action, decision, and LLM call is tracked, costed, and logged.
4.  **LOCAL ONLY:** Your code never leaves your machine. All state is kept in `.synapse/synapse.db`.
5.  **MIRROR GIT EXACTLY:** Synapse's state machine is perfectly synced to `HEAD`.

---

## 🏗️ Architecture: The 3-Layer Context

Synapse provides three distinct layers of context to completely ground the agent:

<p align="center">
  <img src="assets/retrieval-pipeline.svg" alt="Synapse Architecture" width="700">
</p>

### 🧬 L1: Structural (The Truth)
Deterministic mapping of code architecture using **Tree-sitter**.
- Fast, 100% accurate symbol extraction.
- Graph edges mapping `Imports`, `Inherits`, `Calls`, and `References`.

### 📚 L2: Semantic (The "Why")
Hierarchical generated documentation stored locally as Markdown files (`.synapse/wiki/`).
- **File Level:** What does this file do?
- **Module Level:** How do these files relate?
- **Project Level:** `overview.md` and `architecture.md`.

### 🧠 L3: Behavioral (Agent Memory)
Synapse tracks the *history* of agent actions so the AI doesn't repeat past mistakes.
- **Checkpoints:** The active task the agent is performing (`synapse checkpoint`).
- **Decisions:** Architecture decisions logged by the agent.
- **Lessons:** Generated automatically when you run `git revert` on an agent's commit!

---

## 🔄 How it Works

### 1. Git Mirroring
Synapse's daemon watches your repository. Every `git checkout` or `git commit` triggers an immediate state update.

### 2. Context Injection
When an Agent starts a task, it receives a strict, pre-packaged header injection via MCP.

<p align="center">
  <img src="assets/cli-screenshot.svg" alt="CLI Screenshot" width="600">
</p>

---

## 🚀 Quick Start

### 1. Install
```bash
uv tool install synapse-runtime
```

### 2. Setup
```bash
synapse setup .
synapse init .
```

### 3. Start
```bash
synapse start .
```

### 4. Connect
Add Synapse to your MCP-capable IDE (Cursor, Windsurf, Claude Desktop):
```bash
synapse mcp start .
```

---

## 🗺️ Roadmap

- **v0.2.0 (Target: June 2026):** Multi-language expansion (Rust, Go, C/C++).
- **v0.3.0:** Deep Structural Analysis & Cross-repo dependency resolution.
- **v1.0.0:** Production Maturity & Team-wide indexing.

---

## 🤝 Community & Contributing

Synapse is built on the philosophy that AI tools must be transparent and controllable.

- **Spec-First:** Adhere to the `SYNAPSE_BUILD_SPEC.md` strictly.
- **Deterministic:** No implicit RAG features.

License: [Apache 2.0](LICENSE.md)
