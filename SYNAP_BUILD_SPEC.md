# SYNAP — COMPLETE BUILD SPECIFICATION
**Version:** 1.0
**Status:** Build-Ready
**Audience:** Developer / Agent Implementation Guide

---

## TABLE OF CONTENTS

1. [Vision & Philosophy](#1-vision--philosophy)
2. [System Architecture — HLD](#2-system-architecture--hld)
3. [Component Specifications — LLD](#3-component-specifications--lld)
4. [Storage Schemas](#4-storage-schemas)
5. [Data Flows](#5-data-flows)
6. [CLI Reference](#6-cli-reference)
7. [Setup & Init Flow](#7-setup--init-flow)
8. [Git Mirroring — Full Behavior](#8-git-mirroring--full-behavior)
9. [Context Injection System](#9-context-injection-system)
10. [Checkpointing System](#10-checkpointing-system)
11. [Lesson System](#11-lesson-system)
12. [Wiki Generation](#12-wiki-generation)
13. [Cost Tracking](#13-cost-tracking)
14. [MCP Server — Full Spec](#14-mcp-server--full-spec)
15. [Web UI](#15-web-ui)
16. [Edge Cases & Error Handling](#16-edge-cases--error-handling)
17. [What To Remove](#17-what-to-remove)

---

## 1. VISION & PHILOSOPHY

### The Problem
AI coding agents lose context. Every session starts blind. The agent re-reads files, re-understands the same code, repeats the same mistakes. There is no persistent, meaningful memory of the project.

### What Synap Is
Synap is a **local, git-native project intelligence engine**. It maintains a living, structured understanding of a codebase — what exists, what it means, what happened, what failed — and injects this into AI agents via MCP before every session.

The agent never needs to ask "what does this project do." Synap already told it.

### Core Principles — Never Violate These

```
1. DETERMINISTIC FIRST
   Structural indexing works with zero LLM.
   LLM only enriches. Never replaces.

2. NOTHING HAPPENS SILENTLY
   Every action shown in CLI.
   User always knows what Synap is doing.

3. LOCAL ONLY
   No code leaves the machine unless user explicitly configures an external LLM.
   Embeddings always local.

4. HUMAN IN CONTROL
   Agent proposes. User approves.
   Especially for lessons learned from mistakes.

5. FAIL LOUDLY
   No silent fallbacks. No mock modes in production.
   If something breaks, say exactly what broke and why.

6. MIRROR GIT EXACTLY
   Every git action has a Synap reaction.
   Index state always matches git state.
```

### What Synap Is NOT
- Not a RAG system (agent does not query, Synap injects)
- Not a documentation generator (wiki evolves, it's not static docs)
- Not an AI coding agent (it grounds agents, it is not one)
- Not a cloud service (local only, always)

---

## 2. SYSTEM ARCHITECTURE — HLD

### Layer Model

```
┌─────────────────────────────────────────────────────────────────┐
│                          SYNAPSE                                │
│                                                                 │
│  L1 — CODE GRAPH (deterministic, permanent)                     │
│       symbols · edges · files · hashes · imports               │
│                                                                 │
│  L2 — KNOWLEDGE WIKI (LLM-generated, browsable, regeneratable)  │
│       module descriptions · architecture · schema · concepts   │
│                                                                 │
│  L3 — PROJECT MEMORY (append-only, human-approved)              │
│       decisions · checkpoints · lessons · agent activity       │
└─────────────────────────────────────────────────────────────────┘
```

### Component Map

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLI (Typer)                               │
│   init · start · stop · status · wiki · memory · usage · doctor  │
└───────────────────────────┬──────────────────────────────────────┘
                            │ orchestrates
               ┌────────────▼────────────┐
               │     SynapRuntime      │
               │   (single facade)       │
               └──┬──────┬──────┬────────┘
                  │      │      │
        ┌─────────▼─┐ ┌──▼───┐ ┌▼──────────┐ ┌────────────┐
        │  Daemon   │ │Index │ │   Wiki    │ │  Memory    │
        │(git watch)│ │Engine│ │ Generator │ │  Engine    │
        └─────────┬─┘ └──┬───┘ └┬──────────┘ └────────────┘
                  │      │      │
          ┌───────▼──────▼──────▼──────────┐
          │         synap.db             │
          │  (L1: graph + L3: memory)      │
          └───────────────┬────────────────┘
                          │
          ┌───────────────▼────────────────┐
          │          .synap/wiki/        │
          │      (L2: markdown files)      │
          └───────────────┬────────────────┘
                          │
          ┌───────────────▼────────────────┐
          │         MCP Server             │
          │    (read + write, FastMCP)     │  ← only bridge to agent
          └───────────────┬────────────────┘
                          │
                     AI AGENT
```

### Runtime Modes

```
MODE A — Structural Only (no LLM configured)
  ✓ L1 indexing        ✓ lexical search
  ✓ graph traversal    ✓ context injection (structural only)
  ✗ L2 wiki            ✗ semantic search
  ✗ lessons            ✗ project overview

MODE B — Full Intelligence (LLM configured)
  ✓ Everything in Mode A
  ✓ L2 wiki generation
  ✓ semantic understanding
  ✓ lesson writing
  ✓ checkpoint analysis

THERE IS NO MODE C (mock). Remove from codebase entirely.
```

### Network Boundary

```
STAYS LOCAL (always):
  - L1 indexing
  - L3 memory
  - embeddings (nomic-embed-text)
  - MCP server
  - web UI
  - daemon

CROSSES NETWORK (only if user configured external LLM):
  - L2 wiki generation
  - lesson analysis
  - checkpoint summarization
```

---

## 3. COMPONENT SPECIFICATIONS — LLD

---

### 3.1 DAEMON

**Purpose:** Watch git, react to every git action, keep index in sync. Run persistently.

**Startup behavior:**
```python
def start_daemon(mode: str):
    if mode == "autostart":
        # Register as systemd service (Linux) or launchd plist (macOS)
        register_system_service()
    elif mode == "manual":
        # Run as foreground process, show in CLI
        run_foreground()

    # Either way, start the git watcher
    start_git_watcher()
    start_mcp_server()
    start_web_ui()
```

**Git watcher — event detection:**
```python
class GitWatcher:
    def watch(self):
        last_commit = get_current_commit()
        last_branch = get_current_branch()

        while True:
            current_commit = get_current_commit()
            current_branch = get_current_branch()

            if current_branch != last_branch:
                handle_branch_switch(last_branch, current_branch)

            elif current_commit != last_commit:
                event = classify_commit(last_commit, current_commit)
                # event = COMMIT | REVERT | MERGE | CHERRY_PICK

                if event == REVERT:
                    handle_revert(last_commit, current_commit)
                elif event == MERGE:
                    handle_merge(last_commit, current_commit)
                elif event == COMMIT:
                    handle_commit(last_commit, current_commit)

            last_commit = current_commit
            last_branch = current_branch
            sleep(1)  # Poll every second
```

**How to classify a revert:**
```python
def classify_commit(old_commit, new_commit):
    # A revert is detected when:
    # 1. Commit message starts with "Revert"
    # 2. OR the tree hash of new commit matches a previous ancestor
    msg = get_commit_message(new_commit)
    if msg.lower().startswith("revert"):
        return REVERT

    ancestor_trees = get_ancestor_tree_hashes(new_commit, depth=20)
    if get_tree_hash(new_commit) in ancestor_trees:
        return REVERT

    return COMMIT
```

**Daemon output — always visible:**
```
[Synap] Watching /home/user/myproject on branch main
[Synap] Daemon started — autostart mode
[Synap] MCP server running on port 7822
[Synap] Web UI running on port 7823
```

---

### 3.2 INDEXER

**Purpose:** Scan the repository and build L1 (code graph). Runs on init and on every commit.

**Three passes — always in this order:**

```
Pass 1 — Structural (always runs, zero LLM)
Pass 2 — Wiki (runs only if LLM configured, only on significant changes)
Pass 3 — Lesson (runs only on revert detection)
```

**Pass 1 — Structural Indexer:**
```python
class StructuralIndexer:
    def index_changed_files(self, changed_files: list[str]):
        for file_path in changed_files:
            content = read_file(file_path)
            content_hash = sha256(content)
            file_id = sha256(file_path + content_hash)  # path-scoped, never collides

            existing = db.get_file(file_path)
            if existing and existing.content_hash == content_hash:
                continue  # skip unchanged

            language = detect_language(file_path)
            symbols = parser.parse(file_path, content, language)

            with db.transaction():
                db.upsert_file(file_id, file_path, content_hash, language)
                db.clear_file_symbols(file_id)
                for symbol in symbols:
                    db.insert_symbol(symbol)
                db.update_edges(file_id, symbols)

    def full_index(self, repo_root: str):
        all_files = scan_repository(repo_root)  # respects .gitignore
        self.index_changed_files(all_files)
        db.set_active_commit(get_current_commit(), get_current_branch())
```

**File ID — critical fix:**
```python
# WRONG (crashes on duplicate content like empty __init__.py):
file_id = sha256(content)

# CORRECT (path-scoped, always unique):
file_id = sha256(file_path + content_hash)
```

**Symbol extraction per language:**
```python
SUPPORTED_LANGUAGES = {
    "python":     [".py"],
    "typescript": [".ts", ".tsx"],
    "javascript": [".js", ".jsx"],
    "go":         [".go"],
    "rust":       [".rs"],
    "java":       [".java"],
    "cpp":        [".cpp", ".h"],
    "ruby":       [".rb"],
}

SYMBOL_KINDS = [
    "function", "class", "method", "interface",
    "enum", "constant", "variable", "module", "type"
]
```

**Edge type taxonomy — exhaustive enum:**
```python
class EdgeType(str, Enum):
    IMPORT      = "IMPORT"       # file A imports file B
    INHERITS    = "INHERITS"     # class A extends class B
    IMPLEMENTS  = "IMPLEMENTS"   # class A implements interface B
    REFERENCES  = "REFERENCES"   # symbol A references symbol B
    DEFINES_IN  = "DEFINES_IN"   # symbol A defined inside symbol B
    CALLS       = "CALLS"        # symbol A calls symbol B (future)
```

---

### 3.3 PARSER

**Purpose:** Tree-sitter based AST parsing. Extracts symbols from source files.

```python
class Parser:
    def parse(self, file_path: str, content: str, language: str) -> list[Symbol]:
        tree = get_tree_sitter_parser(language).parse(content.encode())
        visitor = SymbolVisitor(file_path, language)
        visitor.visit(tree.root_node)
        return visitor.symbols

    def get_tree_sitter_parser(self, language: str):
        # Lazy load and cache parsers
        if language not in self._parsers:
            self._parsers[language] = load_parser(language)
        return self._parsers[language]
```

**Symbol data model:**
```python
@dataclass
class Symbol:
    symbol_id:   str   # sha256(file_id + name + kind + start_line)
    file_id:     str
    name:        str
    kind:        str   # from SYMBOL_KINDS
    start_line:  int
    end_line:    int
    ast_hash:    str   # hash of the AST subtree
    source:      str   # raw source text of the symbol
    metadata:    dict  # language-specific extras (decorators, visibility, etc.)
```

---

### 3.4 RETRIEVAL ENGINE

**Purpose:** Given a query, find relevant context. Used for context injection, not user queries.

**Hybrid retrieval — three signals combined:**
```python
def retrieve(query: str, budget_tokens: int) -> RetrievalResult:
    # Signal 1: Lexical (exact name match)
    lexical_matches = db.get_symbols_by_name(query)

    # Signal 2: Semantic (embedding similarity) — only in Mode B
    if embedding_available():
        query_embedding = embed(query)
        semantic_matches = db.search_embeddings(query_embedding, top_k=20)
    else:
        semantic_matches = []

    # Signal 3: Structural (graph traversal from seed nodes)
    seed_symbols = deduplicate(lexical_matches + semantic_matches)
    structural_matches = db.get_neighborhood(seed_symbols, max_distance=2)

    # Score and rank
    all_symbols = rank(lexical_matches, semantic_matches, structural_matches)

    # Pack within token budget
    return pack_context(all_symbols, budget_tokens)

def rank(lexical, semantic, structural) -> list[RankedSymbol]:
    scores = {}
    for s in lexical:
        scores[s.symbol_id] = scores.get(s.symbol_id, 0) + 0.5
    for s in semantic:
        scores[s.symbol_id] = scores.get(s.symbol_id, 0) + 0.3
    for s in structural:
        decay = 0.8 ** s.graph_distance
        scores[s.symbol_id] = scores.get(s.symbol_id, 0) + (0.2 * decay)

    return sorted(scores.keys(), key=lambda id: scores[id], reverse=True)
```

**Token budgeting:**
```python
TOKENIZER_MAP = {
    "openai":    "cl100k_base",
    "anthropic": "cl100k_base",  # overestimates ~10-15%, safe underfill
    "gemini":    "cl100k_base",  # approximation
    "ollama":    "cl100k_base",  # model-dependent, safe default
}

def pack_context(symbols: list, budget: int) -> RetrievalResult:
    packed = []
    used = 0
    for symbol in symbols:
        tokens = count_tokens(symbol.source)
        if used + tokens > budget:
            break
        packed.append(symbol)
        used += tokens
    return RetrievalResult(symbols=packed, tokens_used=used)
```

---

### 3.5 STORAGE ENGINE

**Purpose:** Single SQLite database for L1 and L3. Markdown files for L2.

**One database only:** `synap.db`

**File layout:**
```
.synap/
  config.json      ← user preferences
  synap.db       ← L1 code graph + L3 memory
  wiki/            ← L2 knowledge (markdown)
    overview.md
    architecture.md
    schema.md
    modules/
      [module_name].md
    agent/
      decisions.md
      lessons.md
```

**Config schema:**
```json
{
  "llm_provider": "anthropic",
  "llm_model": "claude-sonnet-4-20250514",
  "embedding_model": "nomic-embed-text",
  "daemon_mode": "autostart",
  "checkpoint_threshold": 0.60,
  "mcp_port": 7822,
  "ui_port": 7823,
  "wiki_update_threshold": 10,
  "lesson_expiry_days": 7,
  "version": "1.0"
}
```

---

## 4. STORAGE SCHEMAS

### synap.db — Full Schema

```sql
-- L1: FILES
CREATE TABLE files (
    file_id       TEXT PRIMARY KEY,  -- sha256(path + content_hash)
    path          TEXT UNIQUE NOT NULL,
    content_hash  TEXT NOT NULL,
    git_oid       TEXT,
    language      TEXT,
    updated_at    INTEGER NOT NULL
);

-- L1: SYMBOLS
CREATE TABLE symbols (
    symbol_id    TEXT PRIMARY KEY,  -- sha256(file_id + name + kind + start_line)
    file_id      TEXT NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    start_line   INTEGER NOT NULL,
    end_line     INTEGER NOT NULL,
    ast_hash     TEXT NOT NULL,
    source       TEXT NOT NULL,  -- raw source text
    metadata_json TEXT
);

-- L1: EDGES
CREATE TABLE edges (
    edge_id        TEXT PRIMARY KEY,  -- sha256(source + target + type)
    source_symbol  TEXT NOT NULL REFERENCES symbols(symbol_id) ON DELETE CASCADE,
    target_symbol  TEXT NOT NULL REFERENCES symbols(symbol_id) ON DELETE CASCADE,
    edge_type      TEXT NOT NULL,  -- IMPORT | INHERITS | IMPLEMENTS | REFERENCES | DEFINES_IN
    UNIQUE(source_symbol, target_symbol, edge_type)
);

-- L1: EMBEDDINGS (local only)
CREATE TABLE embeddings (
    embedding_id  TEXT PRIMARY KEY,
    symbol_id     TEXT NOT NULL REFERENCES symbols(symbol_id) ON DELETE CASCADE,
    model_name    TEXT NOT NULL,
    vector        BLOB NOT NULL,  -- float32 array, serialized
    content_hash  TEXT NOT NULL,  -- invalidate if symbol source changes
    created_at    INTEGER NOT NULL
);

-- L1: ACTIVE STATE
CREATE TABLE active_state (
    branch          TEXT PRIMARY KEY,
    git_commit_hash TEXT NOT NULL,
    updated_at      INTEGER NOT NULL
);

-- L3: AGENT DECISIONS
CREATE TABLE decisions (
    decision_id  TEXT PRIMARY KEY,
    branch       TEXT NOT NULL,
    commit_hash  TEXT NOT NULL,
    content      TEXT NOT NULL,  -- what was decided
    context      TEXT,           -- why
    agent_id     TEXT,
    created_at   INTEGER NOT NULL
);

-- L3: AGENT CHECKPOINTS
CREATE TABLE checkpoints (
    checkpoint_id  TEXT PRIMARY KEY,
    branch         TEXT NOT NULL,
    commit_hash    TEXT NOT NULL,
    doing          TEXT NOT NULL,   -- what agent was doing
    changed_files  TEXT NOT NULL,   -- JSON array
    next_step      TEXT,            -- what agent planned to do next
    decisions      TEXT,            -- JSON array of decisions this session
    blockers       TEXT,            -- JSON array
    token_count    INTEGER,
    created_at     INTEGER NOT NULL
);

-- L3: LESSONS (from reverts)
CREATE TABLE lessons (
    lesson_id     TEXT PRIMARY KEY,
    branch        TEXT NOT NULL,
    revert_commit TEXT NOT NULL,    -- the revert commit hash
    reverted_from TEXT NOT NULL,    -- the commit that was reverted
    what_failed   TEXT NOT NULL,    -- what the agent tried
    why_failed    TEXT NOT NULL,    -- analysis of why it broke
    files_affected TEXT NOT NULL,   -- JSON array
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | expired
    created_at    INTEGER NOT NULL,
    approved_at   INTEGER,
    expires_at    INTEGER NOT NULL  -- created_at + 7 days in seconds
);

-- L3: AGENT ACTIVITY LOG
CREATE TABLE activity (
    activity_id  TEXT PRIMARY KEY,
    branch       TEXT NOT NULL,
    commit_hash  TEXT NOT NULL,
    action       TEXT NOT NULL,  -- what the agent did
    files        TEXT,           -- JSON array of affected files
    created_at   INTEGER NOT NULL
);

-- INDEXES
CREATE INDEX idx_symbols_file ON symbols(file_id);
CREATE INDEX idx_symbols_name ON symbols(name);
CREATE INDEX idx_edges_source ON edges(source_symbol);
CREATE INDEX idx_edges_target ON edges(target_symbol);
CREATE INDEX idx_lessons_status ON lessons(status);
CREATE INDEX idx_checkpoints_branch ON checkpoints(branch);
CREATE INDEX idx_activity_branch ON activity(branch);
```

---

## 5. DATA FLOWS

### 5.1 Init Flow (First Run)

```
synap init
    │
    ├── [1] Environment check (synap doctor inline)
    │       git repo exists?
    │       tree-sitter parsers installed?
    │       SQLite writable?
    │       .gitignore present?
    │       → FAIL LOUDLY if any check fails
    │
    ├── [2] Choose LLM provider
    │       OpenAI / Anthropic / Gemini / Ollama / Skip (Mode A)
    │       → store API key via keyring → env var → file fallback
    │
    ├── [3] Embedding model
    │       always local: nomic-embed-text
    │       → download if not present, show progress
    │
    ├── [4] Daemon mode
    │       Autostart (system service) / Manual (synap start)
    │
    ├── [5] Repository indexing — Pass 1 (always)
    │       scan all files (respects .gitignore)
    │       parse symbols
    │       build edges
    │       generate embeddings
    │       → show real-time progress with cost tracker
    │
    ├── [6] Wiki generation — Pass 2 (if LLM configured)
    │       file level → module level → project level
    │       → write .synap/wiki/
    │
    ├── [7] MCP config output
    │       show JSON block, do NOT auto-patch
    │
    └── [8] Open web UI → localhost:7823
```

### 5.2 Commit Flow (Every Commit)

```
git commit
    │
    ├── Daemon detects new commit hash
    ├── Diff changed files
    ├── Pass 1: reindex changed files only
    ├── Check: is this a revert?
    │       YES → trigger Lesson Flow
    │       NO  → continue
    ├── Pass 2: regenerate wiki for changed modules
    │           only if change_score > threshold (see Wiki section)
    ├── Notify CLI: "[Synap] 4 files reindexed · wiki updated"
    └── Update active_state in synap.db
```

### 5.3 Revert Flow

```
git revert (detected by daemon)
    │
    ├── Compute diff: reverted_commit vs current
    ├── Extract: what files changed, what symbols removed/changed
    ├── LLM analyzes:
    │     - what approach was being attempted
    │     - what broke (from diff context)
    │     - why it likely failed
    │
    ├── Propose lesson → status: "pending"
    ├── Notify user in CLI:
    │     ⚠ Revert detected. Agent has proposed a lesson.
    │     Run `synap lessons review` to approve.
    │
    └── Lesson sits in pending until user reviews
        → approved: stored permanently
        → rejected: deleted
        → ignored 7 days: expires automatically
```

### 5.4 Context Injection Flow (Every Agent Session)

```
Agent starts (MCP connection established)
    │
    ├── Synap automatically pushes:
    │     - project overview (from wiki/overview.md)
    │     - current branch state
    │     - recent commits (last 5)
    │     - active checkpoint (if any)
    │     - approved lessons (all time)
    │     - pending lessons (marked as unverified)
    │     - recent decisions (last 10)
    │
    ├── Agent receives full context before writing one line
    │
    └── Agent begins work with complete project understanding
```

### 5.5 Checkpoint Flow

```
Agent monitors own token usage
    │
    ├── Hits 60% of context window
    │
    ├── Agent calls synapse.checkpoint({
    │     doing:    "what I am currently working on",
    │     changed:  ["list", "of", "modified", "files"],
    │     next:     "what I was about to do next",
    │     decisions: ["decisions made this session"],
    │     blockers:  []
    │   })
    │
    ├── Stored in checkpoints table
    ├── CLI notification: "[Synap] Agent checkpointed at 60% — session saved"
    │
    └── New session starts → checkpoint loaded → agent continues
```

### 5.6 Branch Switch Flow

```
git checkout other-branch
    │
    ├── Daemon detects branch change
    │
    ├── Is agent currently active?
    │     YES →
    │       ⚠ Agent is active on [main]
    │         Files in context: 12
    │         Unsaved decisions: 3
    │
    │         [C] Checkpoint and switch
    │         [W] Switch without saving
    │         [A] Abort switch
    │
    │         User chooses C:
    │           → agent forced checkpoint
    │           → index switches to other-branch
    │           → load other-branch context
    │
    │     NO → switch immediately, notify
    │
    └── ✓ Switched to other-branch
          Loaded 2 previous decisions
          1 active checkpoint restored
```

### 5.7 API Key Loading (Priority Chain)

```python
def load_api_key(provider: str) -> str:
    # 1. Environment variable (CI/CD, Docker)
    key = os.environ.get(f"SYNAP_{provider.upper()}_API_KEY")
    if key:
        return key

    # 2. System keyring (interactive installs)
    try:
        import keyring
        key = keyring.get_password("synap", provider)
        if key:
            return key
    except Exception:
        logger.warning("keyring unavailable — trying file fallback")

    # 3. Encrypted credentials file (~/.synap/credentials, chmod 600)
    cred_path = Path.home() / ".synap" / "credentials"
    if cred_path.exists():
        creds = json.loads(cred_path.read_text())
        if provider in creds:
            return creds[provider]

    # 4. HARD FAIL — never silent
    raise SynapConfigError(
        f"\n✗ No API key found for {provider}\n"
        f"  Set SYNAP_{provider.upper()}_API_KEY\n"
        f"  or run: synap setup\n"
    )
```

---

## 6. CLI REFERENCE

### Design Principles
- Every command shows what it's doing, always
- Interactive prompts for destructive actions
- No flags required for common paths
- Color-coded output: ✓ green, ⚠ yellow, ✗ red
- Every command has `--help` that explains exactly what it touches on disk

---

### CORE COMMANDS

#### `synap init`
First-run setup. Runs environment check, setup wizard, full index.
```
synap init

Options:
  --skip-llm       Index structurally only (Mode A)
  --skip-wiki      Skip wiki generation
  --quiet          No interactive prompts, use defaults
```

#### `synap start`
Start the daemon manually (if daemon mode is manual).
```
synap start

Output:
  [Synap] Starting daemon...
  [Synap] Watching /home/user/myproject
  [Synap] MCP server → port 7822
  [Synap] Web UI    → localhost:7823
  [Synap] Ready. Press Ctrl+C to stop.
```

#### `synap stop`
Stop the daemon.
```
synap stop

Options:
  --force    Stop even if agent is active (checkpoint first)
```

#### `synap status`
Full system state at a glance.
```
synap status

Output:
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Synap Status
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Daemon        ✓ running (autostart)
  Branch        main (commit a3f9c2)
  Index         ✓ clean (last: 2 min ago)
  Dirty files   ⚠ 3 files modified, not committed
  MCP           ✓ connected (Claude Desktop)
  Wiki          ✓ current
  Pending       ⚠ 1 lesson awaiting approval
  Agent         ✓ active checkpoint loaded

  Files indexed   487
  Symbols         12,400
  Decisions       23
  Lessons         4 approved · 1 pending
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### INDEX COMMANDS

#### `synap index`
Manually trigger reindex of changed files.
```
synap index

Options:
  --full     Nuke index and rebuild from scratch
             ⚠ Prompts for confirmation before running
```

#### `synap doctor`
Validate entire environment. Run before reporting bugs.
```
synap doctor

Output:
  Checking environment...
  ✓ Git repository found
  ✓ Tree-sitter parsers installed (Python, TypeScript, Go)
  ✓ SQLite writable
  ✓ nomic-embed-text model available
  ✓ LLM provider configured (Anthropic)
  ✓ MCP port 7822 available
  ✓ Web UI port 7823 available
  ✓ .gitignore present
  ✗ keyring: DBus unavailable — using file fallback

  1 warning. System functional.

Options:
  --fix      Attempt to auto-fix warnings
  --context  Show what was injected in last agent session
```

---

### MEMORY COMMANDS

#### `synap memory`
Show project memory overview.
```
synap memory

Output:
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Project Memory — main branch
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Active Checkpoint
    Working on: refactoring auth module
    Changed: src/auth/jwt.ts, src/auth/middleware.ts
    Next: update tests
    Saved: 14 min ago

  Recent Decisions (last 5)
    [2h ago]  Removed refresh token logic — too complex for MVP
    [1d ago]  Switched from Express to Fastify for performance
    ...

  Approved Lessons (4)
    → Avoid circular imports in src/indexer/ — crashes parser
    → JWT middleware must run before rate limiter, not after
    ...

  Pending Lessons (1)
    ⚠ [needs review] Failed attempt at async symbol extraction
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Options:
  --branch NAME    Show memory for a different branch
  --full           Show all decisions, all time
```

#### `synap lessons`
Manage lessons learned from reverts.
```
synap lessons           # list all lessons
synap lessons review    # interactive approval flow for pending lessons
synap lessons show ID   # show a specific lesson in detail
synap lessons delete ID # delete an approved lesson
```

**`synap lessons review` interactive flow:**
```
⚠ 1 Pending Lesson — Requires Your Review
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Revert detected: commit b4a92f (2 hours ago)
Files affected: src/indexer/engine.py, src/parser/visitor.py

What was attempted:
  Async symbol extraction using asyncio.TaskGroup
  to parallelize Tree-sitter parsing

What broke:
  Tree-sitter parsers are not thread-safe. Running
  concurrent parse calls on the same language parser
  instance caused data corruption in the AST output.

Lesson proposed:
  "Do not use concurrent/async calls on Tree-sitter
  parser instances. Each parse must be sequential or
  use separate parser instances per thread."

[A] Approve and store
[E] Edit before storing
[R] Reject — do not store
> _
```

#### `synap checkpoint`
Manual checkpoint (agent also calls this automatically).
```
synap checkpoint         # create checkpoint of current agent state
synap checkpoint list    # list all checkpoints
synap checkpoint restore # restore most recent checkpoint
synap checkpoint restore --id ID
```

---

### WIKI COMMANDS

#### `synap wiki`
Open the project wiki in browser.
```
synap wiki              # open localhost:7823/wiki
synap wiki update       # force regenerate entire wiki
synap wiki update --module src/auth   # regenerate one module only
synap wiki show overview              # print overview.md to terminal
```

---

### COST COMMANDS

#### `synap cost`
Token usage and cost breakdown.
```
synap cost

Output:
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Token Usage & Cost
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Provider      Anthropic (claude-sonnet-4)

  Init          187,420 tokens   $0.31
  Commits       12,340  tokens   $0.02  (47 commits)
  Wiki updates  8,200   tokens   $0.01
  Lessons       2,100   tokens   $0.003
  ───────────────────────────
  Total         210,060 tokens   $0.34

  Avg per commit: ~$0.0004

Options:
  --today      Today only
  --week       Last 7 days
  --breakdown  Per-file cost breakdown
```

---

### GIT MIRROR COMMANDS

#### `synap branch`
Show current branch context.
```
synap branch

Output:
  Current branch: main (commit a3f9c2)
  Index state:    clean
  Other branches: feature/auth (indexed), fix/typo (indexed)
```

#### `synap rollback`
Roll index back to a previous commit's state.
```
synap rollback

Output:
  Recent commits:
  [1] a3f9c2  2h ago   "fix: auth middleware order"  ← current
  [2] b4a92f  4h ago   "feat: async symbol extraction"
  [3] c91d3e  1d ago   "refactor: split indexer engine"
  [4] d02e4f  2d ago   "init: project setup"

  Roll back to which commit? [1-4]: _

  ⚠ Rolling back to c91d3e will:
    - Restore index to that commit's state
    - Preserve all approved lessons (they survive rollbacks)
    - Clear current checkpoint

  Proceed? [y/N]: _
```

#### `synap recover`
Rebuild index from git history if synap.db is corrupted.
```
synap recover

Output:
  ✗ synap.db appears corrupted

  Rebuilding from git history...
  [1/3] Restoring file structure from HEAD
  [2/3] Reindexing all symbols
  [3/3] Regenerating wiki from last known state

  ✓ Recovery complete. 487 files restored.
  ⚠ Agent memory (L3) could not be recovered — starting fresh.
```

---

### MCP COMMANDS

#### `synap mcp`
MCP server management.
```
synap mcp status     # show connection health
synap mcp config     # output config block for agent setup
synap mcp verify     # verify agent can connect
synap mcp restart    # restart MCP server
```

**`synap mcp config` output:**
```
Add the following to your agent's MCP config:

─── Cursor ──────────────────────────────────────
{
  "mcpServers": {
    "synap": {
      "command": "synap",
      "args": ["mcp", "serve"],
      "env": {}
    }
  }
}
Config file: ~/.cursor/mcp.json
─────────────────────────────────────────────────

Run `synap mcp verify` after adding to confirm connection.

Options:
  --target cursor|claude|vscode|windsurf|manual
```

---

## 7. SETUP & INIT FLOW

### Full Init UX

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Synap — First Run Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Checking environment...
  ✓ Git repository: /home/user/myproject
  ✓ Tree-sitter parsers available
  ✓ SQLite writable
  ✓ Filesystem permissions OK

Choose LLM provider for project intelligence:
  [1] OpenAI (GPT-4o)
  [2] Anthropic (Claude Sonnet)
  [3] Gemini (Gemini 1.5 Pro)
  [4] Ollama (local, fully offline)
  [5] Skip — structural index only (free, no AI features)

> 2

Enter Anthropic API key: ****************************
  ✓ Key valid. Stored securely.

Embedding model: nomic-embed-text (local, always private)
  Downloading model... [████████████] 274MB ✓

Daemon mode:
  [1] Autostart — runs on system boot, always watching
  [2] Manual — start with `synap start` when needed

> 1
  ✓ Registered as system service

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Building Project Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1/4] Scanning repository
      ✓ 487 files · TypeScript (234) · Python (156) · Go (97)
      Tokens: 0

[2/4] Building structural index
      Parsing TypeScript    [████████████] 234/234 files
      Parsing Python        [████████████] 156/156 files
      Parsing Go            [████████████]  97/97  files
      Extracting symbols    ✓ 12,400 symbols · 3,200 edges
      Generating embeddings [████████░░░░] 8,200/12,400
      Tokens: 0

[3/4] Generating knowledge wiki
      src/indexer/          ✓ analyzed  (1,240 tokens)
      src/retrieval/        ✓ analyzed  (980  tokens)
      src/mcp/              ⟳ analyzing...
      src/api/              ░ queued
      ...
      Writing overview.md...
      Writing architecture.md...
      Tokens used: 187,420

[4/4] Finalizing
      ✓ Project memory initialized
      ✓ MCP server ready

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Synap Ready
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Files indexed       487
  Symbols extracted   12,400
  Wiki pages          23

  Time taken          2m 14s
  Tokens used         187,420

  Next: Connect your AI agent
  Run: synap mcp config

  Wiki: localhost:7823
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 8. GIT MIRRORING — FULL BEHAVIOR

Every git action maps to a Synap reaction. All automatic. All visible.

```
Git Action               Synap Reaction
──────────────────────────────────────────────────────────────────
git commit               Reindex changed files
                         Update wiki for changed modules (if score > threshold)
                         Log to activity table
                         CLI: "[Synap] 4 files reindexed · 2min"

git checkout [branch]    Warn if agent active → checkpoint prompt
                         Switch index to that branch
                         Load branch checkpoints and decisions
                         CLI: "✓ Switched to feature/auth · 3 decisions loaded"

git checkout -b [branch] Create new index entry for branch
                         Inherit from parent:
                           ✓ project overview wiki
                           ✓ architecture wiki
                           ✓ global approved lessons
                           ✗ parent branch decisions (stays on parent)
                           ✗ parent branch checkpoints (stays on parent)
                         CLI: "✓ New branch feature/auth · inherited global context"

git revert              Detect revert (commit message or tree hash match)
                         Diff before/after
                         LLM analyzes failure
                         Create pending lesson
                         CLI: "⚠ Revert detected · 1 lesson pending review"

git merge               Merge both branch indexes
                         Wiki conflict: show diff, user resolves
                         Decisions: merge both, mark branch origin
                         CLI: "✓ Merged context · 2 wiki conflicts to resolve"

git stash               Snapshot current context to checkpoints table
                         Mark as stash type
                         CLI: "[Synap] Context stashed"

git stash pop           Restore stash checkpoint
                         CLI: "[Synap] Context restored from stash"

git tag                 Record tag in active_state metadata
                         CLI: "[Synap] Tag v1.0.0 recorded"
```

### Dirty Tree Detection

Run before every context injection:

```python
def check_dirty_tree(repo) -> DirtyWarning | None:
    if repo.is_dirty(untracked_files=False):
        dirty_files = [item.a_path for item in repo.index.diff(None)]
        return DirtyWarning(
            files=dirty_files,
            commit=repo.head.commit.hexsha[:8],
            message=f"⚠ {len(dirty_files)} modified files not yet committed. "
                    f"Agent context may not match reported commit {commit}."
        )
    return None
```

Surface this warning in:
- CLI status output
- Retrieval trace
- Context injection header to agent

---

## 9. CONTEXT INJECTION SYSTEM

### What Gets Injected (Every Session)

```python
def build_injection_context(branch: str) -> InjectionContext:
    return InjectionContext(
        # Always injected
        project_overview=read_wiki("overview.md"),
        current_branch=branch,
        current_commit=get_active_commit(branch),
        dirty_warning=check_dirty_tree(),

        # Recent history
        recent_commits=get_recent_commits(limit=5),
        recent_decisions=get_decisions(branch, limit=10),

        # Memory
        active_checkpoint=get_latest_checkpoint(branch),

        # Lessons
        approved_lessons=get_lessons(status="approved"),
        pending_lessons=get_lessons(status="pending"),  # marked as unverified

        # Architecture
        architecture_summary=read_wiki("architecture.md"),
    )
```

### Injection Header Sent to Agent

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SYNAPSE CONTEXT — main (a3f9c2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[project overview here]

ACTIVE CHECKPOINT:
  Working on: refactoring auth module
  Changed files: src/auth/jwt.ts, src/auth/middleware.ts
  Next step: update tests after middleware change
  Saved: 14 min ago

APPROVED LESSONS (apply always):
  [1] Do not use async on Tree-sitter parser instances
  [2] JWT middleware must run before rate limiter

PENDING LESSONS (unverified — use with caution):
  [1] ⚠ Async symbol extraction failed — awaiting user review

RECENT DECISIONS:
  [2h ago] Removed refresh token logic — too complex
  [1d ago] Switched to Fastify for performance

⚠ DIRTY TREE: 3 files modified since a3f9c2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 10. CHECKPOINTING SYSTEM

### Agent-Side Behavior

Agent monitors its own token usage. At 60% capacity:

```python
# Agent calls this MCP tool
synapse.checkpoint({
    "doing":     "refactoring auth middleware to run before rate limiter",
    "changed":   ["src/auth/jwt.ts", "src/auth/middleware.ts"],
    "next":      "update tests in src/auth/__tests__/middleware.test.ts",
    "decisions": ["JWT must run before rate limiter per RFC 6749"],
    "blockers":  []
})
```

### Checkpoint Stored In DB

```sql
INSERT INTO checkpoints VALUES (
    checkpoint_id,
    branch,
    commit_hash,
    doing,
    changed_files,  -- JSON
    next_step,
    decisions,      -- JSON
    blockers,       -- JSON
    token_count,    -- 60% of context window
    created_at
)
```

### On New Session

```python
def inject_checkpoint(branch: str) -> str | None:
    checkpoint = db.get_latest_checkpoint(branch)
    if not checkpoint:
        return None

    age_minutes = (now() - checkpoint.created_at) / 60

    return f"""
ACTIVE CHECKPOINT (saved {age_minutes:.0f} min ago):
  Was doing: {checkpoint.doing}
  Changed: {', '.join(checkpoint.changed_files)}
  Next step: {checkpoint.next_step}
  Decisions made: {checkpoint.decisions}
"""
```

### Checkpoint at Branch Switch

```python
def force_checkpoint_before_switch(agent_connection):
    if agent_connection.is_active():
        # Send signal to agent via MCP
        agent_connection.send_signal("CHECKPOINT_NOW", {
            "reason": "branch switch imminent"
        })
        # Wait up to 30 seconds for checkpoint
        wait_for_checkpoint(timeout=30)
```

---

## 11. LESSON SYSTEM

### Full Lesson Lifecycle

```
REVERT DETECTED
    ↓
status = "pending"
    ↓
User notified in CLI
    ↓
          User reviews in `synap lessons review`
         /              |               \
    APPROVE           EDIT            REJECT
        ↓               ↓               ↓
  status=approved  edit+approve    status=rejected
  stored forever    stored         deleted

    If ignored 7 days → status=expired → soft deleted
```

### Lesson Analysis Prompt (sent to LLM)

```python
def build_lesson_prompt(diff: str, reverted_commit_msg: str, changed_files: list) -> str:
    return f"""
You are analyzing a git revert to extract a lesson for future AI coding sessions.

Reverted commit message: {reverted_commit_msg}
Files affected: {', '.join(changed_files)}

Code diff (what was removed by the revert):
{diff}

Write a concise lesson with:
1. What approach was attempted (1-2 sentences)
2. What broke and why (2-3 sentences, technical)
3. The lesson to remember (1 sentence, actionable)

Be specific. Reference actual file paths and function names from the diff.
Do not be vague. This will be injected into future AI sessions.
"""
```

### Pending Lessons in Agent Context

```python
# Pending lessons are injected but clearly marked
for lesson in pending_lessons:
    context += f"⚠ UNVERIFIED LESSON (pending user approval):\n{lesson.content}\n"
```

Agent sees them but knows they're unverified. Uses judgment.

### Lesson Expiry Job

```python
# Runs daily as part of daemon
def expire_old_lessons():
    db.execute("""
        UPDATE lessons
        SET status = 'expired'
        WHERE status = 'pending'
        AND expires_at < ?
    """, [now()])
```

---

## 12. WIKI GENERATION

### Three-Level Generation

```
Level 1 — File level (parallel, 20 files at once)
    Each file → LLM → description + key exports + responsibilities

Level 2 — Module level (sequential after Level 1)
    Group of related files → LLM → module summary + interfaces

Level 3 — Project level (after all Level 2 complete)
    All module summaries → LLM → overview + architecture + schema
```

### Wiki Update Threshold (prevents expensive regeneration)

```python
def should_regenerate_wiki(module: str, changed_files: list) -> bool:
    # Count significant changes (not just formatting/comments)
    significant_changes = 0
    for file in changed_files:
        diff = get_diff(file)
        if count_structural_changes(diff) > 0:
            significant_changes += 1

    # Only regenerate if 10+ lines of structural change
    total_structural_lines = sum(
        count_structural_changes(get_diff(f)) for f in changed_files
    )
    return total_structural_lines >= 10
```

### Wiki File Structure

```
.synap/wiki/
  overview.md         ← full project summary, entrypoints, app type
  architecture.md     ← how systems connect, data flow
  schema.md           ← database/data models in plain language
  modules/
    [module].md       ← one file per src/ subdirectory
  agent/
    decisions.md      ← rendered from decisions table
    lessons.md        ← rendered from lessons table (approved only)
```

### Wiki Merge Conflict (on `git merge`)

```
⚠ Wiki conflict detected after merge
  Both branches modified: src/auth/ module

  main/modules/auth.md:
    "JWT-based authentication with refresh tokens"

  feature/auth/modules/auth.md:
    "Session-based authentication, JWT removed"

  [K] Keep main version
  [F] Keep feature branch version
  [M] Merge both (agent will synthesize)
  [E] Edit manually
> _
```

---

## 13. USAGE TRACKING

### Every LLM call records usage:

```python
@dataclass
class LLMCall:
    provider:      str
    model:         str
    input_tokens:  int
    output_tokens: int
    purpose:       str  # "wiki_file" | "wiki_module" | "wiki_project" | "lesson"
    file_path:     str | None
    created_at:    int
```

### Usage stored in synap.db:

```sql
CREATE TABLE llm_calls (
    call_id       TEXT PRIMARY KEY,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    purpose       TEXT NOT NULL,
    file_path     TEXT,
    created_at    INTEGER NOT NULL
);
```

### Real-Time Usage in Init Progress

```
[3/4] Generating knowledge wiki
      src/auth/         ✓ analyzed  (1,240 tokens)
      src/indexer/      ⟳ analyzing... (Tokens used: 187,420)
```

---

## 14. MCP SERVER — FULL SPEC

### Server Startup

```python
mcp = FastMCP("synap")
# Runs on port 7822
# Bidirectional: agent reads AND writes
```

### READ TOOLS (agent → Synap)

```python
@mcp.tool()
def get_project_context() -> dict:
    """
    Returns full context injection for new session.
    Called automatically by agent on session start.
    """
    return build_injection_context(get_current_branch())

@mcp.tool()
def get_wiki_page(module: str) -> str:
    """
    Returns the wiki page for a specific module.
    Agent calls when it needs deep context on a specific area.
    """
    path = f".synap/wiki/modules/{module}.md"
    return read_file(path) if exists(path) else f"No wiki page for {module}"

@mcp.tool()
def get_lessons() -> list[dict]:
    """Returns all approved lessons."""
    return db.get_lessons(status="approved")

@mcp.tool()
def get_checkpoint(branch: str = None) -> dict | None:
    """Returns the most recent checkpoint for current or specified branch."""
    return db.get_latest_checkpoint(branch or get_current_branch())

@mcp.tool()
def get_symbols(query: str, limit: int = 20) -> list[dict]:
    """Lexical symbol search for specific lookups."""
    return db.get_symbols_by_name(query, limit=limit)

@mcp.tool()
def get_neighbors(symbol_id: str, depth: int = 2) -> list[dict]:
    """Graph traversal from a symbol."""
    return db.get_neighborhood([symbol_id], max_distance=depth)
```

### WRITE TOOLS (agent → Synap)

```python
@mcp.tool()
def checkpoint(
    doing: str,
    changed: list[str],
    next: str,
    decisions: list[str],
    blockers: list[str] = []
) -> dict:
    """
    Save agent working state. Call at 60% token capacity.
    Never fails silently — raises if storage fails.
    """
    checkpoint_id = create_checkpoint(
        branch=get_current_branch(),
        commit_hash=get_current_commit(),
        doing=doing,
        changed_files=changed,
        next_step=next,
        decisions=decisions,
        blockers=blockers
    )
    notify_cli(f"[Synap] Checkpoint saved — session state preserved")
    return {"checkpoint_id": checkpoint_id, "status": "saved"}

@mcp.tool()
def log_decision(content: str, context: str = "") -> dict:
    """
    Record a decision made during this session.
    Agent calls this when it makes a significant architectural or approach decision.
    """
    decision_id = db.insert_decision(
        branch=get_current_branch(),
        commit_hash=get_current_commit(),
        content=content,
        context=context
    )
    return {"decision_id": decision_id, "status": "logged"}

@mcp.tool()
def log_activity(action: str, files: list[str] = []) -> dict:
    """
    Log what agent is doing. Called on significant actions.
    """
    db.insert_activity(
        branch=get_current_branch(),
        commit_hash=get_current_commit(),
        action=action,
        files=files
    )
    return {"status": "logged"}

@mcp.tool()
def signal_low_context(token_count: int, capacity: int) -> dict:
    """
    Agent signals it is approaching context limit.
    Synap prompts agent to checkpoint immediately.
    """
    percentage = token_count / capacity
    if percentage >= 0.60:
        notify_cli(f"⚠ Agent at {percentage:.0%} context — checkpoint recommended")
    return {"should_checkpoint": percentage >= 0.60}
```

---

## 15. WEB UI

### Routes

```
localhost:7823/              → redirect to /wiki
localhost:7823/wiki          → project wiki home (overview.md rendered)
localhost:7823/wiki/[page]   → individual wiki page
localhost:7823/memory        → project memory dashboard
localhost:7823/memory/lessons → lesson management (approve/reject)
localhost:7823/memory/decisions → all decisions
localhost:7823/memory/checkpoints → checkpoint history
localhost:7823/usage         → token usage breakdown
localhost:7823/status        → live system status (replaces old diagnostic UI)
localhost:7823/index         → raw index explorer (symbols, edges, files)
```

### Real-Time Updates

```python
# Use Server-Sent Events for live updates
@app.get("/events")
async def events():
    async def generate():
        while True:
            event = await event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
    return EventSourceResponse(generate())
```

Events pushed to UI:
- New commit indexed
- Wiki page updated
- Lesson pending
- Agent checkpoint saved
- Branch switch

### Lesson Review in UI

The `/memory/lessons` page shows pending lessons with:
- Full diff view
- Approve / Edit / Reject buttons
- 7-day expiry countdown
- Same flow as CLI but visual

---

## 16. EDGE CASES & ERROR HANDLING

### Index Integrity

```
CASE: Two files with identical content (e.g., empty __init__.py)
  WRONG: file_id = sha256(content)  → UNIQUE constraint crash
  CORRECT: file_id = sha256(path + content_hash)  → always unique
  TEST: Create two empty files in different directories. Index must not crash.

CASE: File deleted from repo
  On next index: detect file missing from filesystem
  Run: db.delete_file(file_id)  → CASCADE deletes symbols and edges
  Wiki page for that module regenerated

CASE: Binary file encountered
  Detect by: checking for null bytes or non-UTF-8 content
  Action: index file record only (path, hash), skip symbol extraction
  Never crash on binary files

CASE: File too large (> 1MB)
  Action: index file record, skip symbol extraction, log warning
  CLI: "⚠ src/data/large_file.json skipped (too large for symbol extraction)"

CASE: Unsupported language
  Action: index file record only, skip parsing
  Never crash
```

### Git Edge Cases

```
CASE: Repository has no commits yet (empty repo)
  synap init must fail clearly:
  "✗ Repository has no commits. Make an initial commit first."

CASE: Detached HEAD state
  Warn user: "⚠ Detached HEAD — branch tracking unavailable"
  Index against the commit hash directly
  Do not crash

CASE: Merge conflict in progress (MERGE_HEAD exists)
  Do not auto-index during active merge conflict
  CLI: "⚠ Merge conflict in progress — indexing paused"
  Resume after merge resolves

CASE: Submodules present
  Do not index submodule contents by default
  Config option: synapse.index_submodules = false (default)
  Warn: "⚠ Submodule detected at vendor/ — skipping (change in config.json)"

CASE: Very large repository (> 500 files — outside target range)
  Warn at init: "⚠ 1,240 files detected. Target is under 500. Init may take longer."
  Continue normally, do not block
```

### LLM & Provider Edge Cases

```
CASE: LLM provider rate limit hit during wiki generation
  Exponential backoff: 1s → 2s → 4s → 8s → 16s
  Show in progress: "⟳ Rate limited — retrying in 4s..."
  Never crash, never skip silently

CASE: LLM returns malformed response
  Retry once with explicit JSON format prompt
  If still malformed: log error, skip that wiki page, continue
  Never block indexing

CASE: LLM provider outage
  L1 indexing continues (structural, no LLM needed)
  L2 wiki generation queued for retry
  L3 lesson analysis queued for retry
  CLI: "⚠ Anthropic API unavailable — wiki update queued"

CASE: API key expires mid-session
  Catch auth error on next LLM call
  CLI: "✗ API key invalid. Run: synap setup"
  Structural features continue working (Mode A fallback)

CASE: Ollama not running (local LLM)
  CLI: "✗ Ollama not responding on localhost:11434"
  "Start Ollama: ollama serve"
  Do not crash
```

### Daemon Edge Cases

```
CASE: Two Synap processes started simultaneously
  Use a lock file: .synap/daemon.lock
  Second process: "✗ Synap already running (PID 12345)"

CASE: Machine goes to sleep mid-index
  On wake: check if index job was interrupted
  If interrupted: restart indexing from last checkpoint
  Never leave synap.db in partial state (SQLite WAL handles this)

CASE: Disk full during indexing
  Catch disk write errors
  CLI: "✗ Disk full — indexing stopped. Free space and run: synap index"
  Do not corrupt existing index

CASE: .synap/synap.db corrupted
  Detect on startup: run PRAGMA integrity_check
  If fails: "✗ Index corrupted. Run: synap recover"
  Never auto-delete without explicit user command
```

### Branch Edge Cases

```
CASE: Checkout with uncommitted changes (git blocks it)
  Git will block, Synap does nothing
  Only react after git succeeds

CASE: Branch deleted remotely, still tracked locally
  Index remains until user deletes branch locally
  Synap mirrors local git state only

CASE: New branch inherits from parent — what exactly?
  INHERIT: project overview, architecture wiki, global lessons
  DO NOT INHERIT: branch decisions, branch checkpoints, branch lessons
  This prevents parent-branch-specific context polluting new branch work

CASE: Merge produces wiki conflict on same module
  Diff both versions, present to user
  [K] Keep one, [M] Merge (LLM synthesizes), [E] Edit manually
  Never auto-resolve silently
```

### Checkpoint Edge Cases

```
CASE: Agent crashes without checkpointing
  On next session: no checkpoint available
  Synap injects: "⚠ No checkpoint found — agent may have exited unexpectedly"
  Still inject all other context (decisions, lessons, overview)

CASE: Checkpoint is very old (> 7 days)
  Still load it, but warn:
  "⚠ Checkpoint is 8 days old — verify files still exist"

CASE: Checkpoint references files that no longer exist (deleted)
  Filter out deleted files from checkpoint context
  Warn: "⚠ 2 files in checkpoint no longer exist: [list]"

CASE: Multiple checkpoints on same branch
  Always restore the MOST RECENT by created_at
  `synap checkpoint list` shows all, user can pick specific one
```

### Lesson Edge Cases

```
CASE: Revert of a revert (double revert)
  Classify as COMMIT not REVERT (restoring good code)
  Do not generate lesson
  Detection: tree hash matches commit 2 levels up

CASE: User rejects all lessons (always rejects)
  No consequence — lessons are optional enrichment
  Agent still works fully without lessons

CASE: Lesson references symbols that no longer exist after revert
  Store lesson as-is (historical record)
  When injecting: note "this lesson references deleted code"

CASE: Two reverts in quick succession
  Both generate separate lessons
  Both pending approval independently
  Do not merge or deduplicate automatically
```

---

## 17. WHAT TO REMOVE

Remove these from the current codebase before building forward:

```
REMOVE: llm_provider = "mock" from SynapSettings
  Replace with: explicit Mode A (no provider) with clear messaging
  Mock belongs in test fixtures ONLY

REMOVE: synap trace command
  Replaced by: synap doctor --context
  Philosophy: agent should not ask specific questions

REMOVE: synap index --full as separate flag
  Replaced by: synap recover (for corruption)
  and: synap rollback (for intentional reset)

REMOVE: synap stash command
  Git stash is automatically mirrored by daemon
  No manual CLI command needed

REMOVE: synap diff command
  Covered by synap status output

REMOVE: synap memory log as separate command
  Covered by synap memory --full

REMOVE: retrieval_traces table from SQLite
  Not needed — trace info now goes into agent context injection header
  Keeps schema clean
```

---

*End of Synap Build Specification v1.0*
*Every component defined. Every edge case covered. Build from top to bottom.*

---

## 18. PERFORMANCE ARCHITECTURE (v1.1.0 UPDATE)

### Git-Snapshot Paradigm
Synapse indexes are designed as projections of Git commit history. Change detection avoids expensive filesystem directory traversing or hashing of files. Instead, Synapse queries the active Git tree:
- **Change detection:** Incremental runs compare the last-indexed commit hash against `HEAD` using `git diff-tree`. Only modified, added, or deleted files are touched.
- **Git OID verification:** Git's own blob object IDs (OIDs) from `git ls-tree` are used as the unique integrity token. If the Git index OID matches the stored OID, the file has not changed (mathematically guaranteed).

### Split Two-Path Architecture
- **Path A: First Run (`_first_run_index`):** A full scan and rebuild. Treesitter parsing is parallelized across all available CPU cores using process-based concurrency (`ProcessPoolExecutor`) with one parser instance per process. Parse results are written to the database in chunks to prevent memory accumulation. Wiki generation tasks are enqueued to a background queue, bypassing the critical path.
- **Path B: Incremental (`_incremental_index`):** Runs only when a prior commit hash is indexed. Bypasses file scans/hashing. Operates in $O(\Delta)$ time by fetching changed files from Git.

### Decoupled Lazy & Asynchronous Wiki Generation
- **Asynchronous Queue:** LLM wiki generation is decoupled from structural indexing. Work is written to `wiki_queue` and consumed by an asynchronous daemon worker loop (`_wiki_worker_loop`).
- **Lazy Caching:** Wiki pages are generated on request and cached. Stale/missing pages are refreshed synchronously when requested via CLI (`wiki show`), API `/wiki`, or MCP.

### SQLite Performance Architecture
- **WAL & Synchronous Mode:** Database operates with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` to optimize concurrent reads and quick writes.
- **Single Transaction Commits:** All symbols, files, and structural edges from an indexing pass are batched and committed within a single transaction, reducing Disk Sync overhead.
- **Batch Insertion:** Uses `executemany` for multi-row symbol and edge inserts.
- **O(1) Module Resolution:** Pre-computes and indexes a dot-separated `module_key` (e.g. `synap_git.storage.sqlite`) during structural parsing, replacing slow `LIKE "%path"` scans.
- **FTS5 Search:** Fast symbol name lookup matches patterns utilizing the SQLite `FTS5` virtual table (`symbols_fts`), completely eliminating leading wildcard `LIKE "%name%"` table scans.

---

*End of Synap Build Specification v1.1.0*
*Every component defined. Every edge case covered. Build from top to bottom.*
