# Architecture Migration Audit

This audit documents the current state of terms, architecture models, and code elements across the Synapse repository. It categorizes them into what stays, what is renamed/re-framed (exclusively in documentation, comments, and strings to preserve API stability), what is deprecated, what is formalized, and what becomes canonical.

---

## 1. What Should Stay (Technical Foundations)

The underlying core mechanics are highly robust, correct, and verified by tests. They must not be altered:
- **SQLite + WAL Storage**: The dual-database model (`SQLiteEventStore` with connection timeouts and `ObjectStore` for content-addressed msgpack blobs) is load-bearing and must remain intact.
- **Stable Hashing**: SHA-256 stable serialization (`serialization.stable_hash`) ensures deterministic identity.
- **Transaction Journaling**: `CognitiveTransactionEngine` is correct, guaranteeing write safety and startup recovery.
- **Deterministic Replay Mechanics**: The `ReplayEngine` bounded playback (snapshot + WAL delta play) is correct and must be kept.
- **AST / LSP Extraction**: The deterministic parsing of Markdown headers and source directories is correct.
- **Validation Constraints**: Zero-power check validations, path traversal protection (`Path.relative_to`), and schema versions are correct.

---

## 2. Terminology Convergence (OLD → NEW)

We will migrate all occurrences of anthropomorphic and vague AI positioning in docs, comments, UI text, and string constants. 
*Note: To avoid breaking APIs, CLI commands, and database serialization, matching code identifiers (classes, methods, table columns) remain unchanged but are conceptually mapped in documentation.*

| Location | Old Terminology | New Canonical Terminology | Scope / File Action |
|---|---|---|---|
| Repository Docs & CLI | "Cognitive OS" / "AI Operating System" | **Temporal Source Context Substrate** | Replace in `README.md`, `VISION.md`, `RELEASE.md`, `docs/**/*.md` |
| Repository Docs & CLI | "Cognitive Runtime" | **Temporal Context Runtime** | Replace in CLI descriptions, API docs, docs, comments |
| Repository Docs & CLI | "Cognition Object" | **Semantic Annotation** | Replace in descriptions of `SemanticObject`, CLI, docs, comments |
| Repository Docs & CLI | "Memory" | **Context State** or **Semantic Overlay** | Replace in docs, comments |
| Repository Docs & CLI | "Confidence Score" | **Validation State** (`Validated`, `Assumed`, `Invalidated`) | Map numeric scores conceptually in docs; update UI with tristate |
| Repository Docs & CLI | "Cognition Replay" | **Temporal Context Replay** | Replace in CLI descriptions, docs, comments |

---

## 3. What Should Be Deprecated or Re-Framed

- **Vague "Infinite Replay" / "Continuous Replay"**: Deprecate the implication of replaying all of execution history from scratch forever. Re-frame replay as **bounded temporal reconstruction** (checkpoint snapshot + WAL log delta).
- **Floating-Point "Truth Confidence"**: Deprecate the notion of floating-point numbers defining absolute architectural truth. Re-frame numeric scores as secondary heuristics; promote the **tristate validation model** as the structural truth.
- **"Cognitive OS" / "AI Memory" Hype**: Remove references to Synapse being an autonomous cognitive agent or an operating system powered by AI. Re-frame it as developer/agent infrastructure for software context evolution.

---

## 4. What Should Be Formalized

We will explicitly formalize the boundary between:
- **Deterministic Structural Truth** (Graph / AST / Git / Lineage): Derived via deterministic parsers, LSP, and commit lineage. AI is never allowed to mutate this truth or define dependencies.
- **Probabilistic Semantic Interpretation** (Semantic Overlays): Versioned annotations, summaries, and inferred assumptions. These are lazy-evaluated, stateless, and remain invalidatable.

---

## 5. What Should Become Canonical

- **Content-Addressed Structural Delta**: The fundamental primitive of history. Every commit is a collection of content-addressed structural changes representing file states, edges, and annotations.
- **Causal Software Evolution Graph**: The projection of context history over time showing causal relationships and branch divergence.
