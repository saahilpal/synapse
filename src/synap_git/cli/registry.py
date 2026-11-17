from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArgumentDef:
    """Definition of a CLI command argument."""

    name: str
    description: str
    required: bool = True
    default: Any = None
    type_name: str = "str"


@dataclass(frozen=True)
class OptionDef:
    """Definition of a CLI command option or flag."""

    flags: tuple[str, ...]
    description: str
    default: Any = None
    is_flag: bool = False
    type_name: str = "str"


@dataclass(frozen=True)
class CommandDef:
    """Authoritative schema definition of a Synapse command."""

    name: str
    one_line_help: str
    description: str
    arguments: tuple[ArgumentDef, ...] = ()
    options: tuple[OptionDef, ...] = ()
    exit_codes: dict[int, str] = field(
        default_factory=lambda: {0: "Successful execution", 1: "Execution or parameter error"}
    )
    output_schema: dict[str, Any] = field(default_factory=dict)
    examples: tuple[str, ...] = ()
    is_core_agent: bool = False
    slash_command: str | None = None
    slash_syntax: str | None = None
    aliases: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Authoritative Command Registry
# ---------------------------------------------------------------------------

_CORE_COMMANDS: list[CommandDef] = [
    CommandDef(
        name="ctx",
        one_line_help="Output high-density, token-bounded context preamble for coding agents and tasks.",
        description="Generates an ultra-compact, token-bounded structural context preamble tailored for an agent task. Slices relevant symbol signatures, callers, dirty git blast radius, and lessons under a strict token budget.",
        arguments=(
            ArgumentDef(
                name="task",
                description="Task description or implementation goal.",
                required=False,
                default="",
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--budget", "-b"),
                description="Token budget preset (dense=500, standard=1500, deep=4000).",
                default="standard",
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Context successfully generated", 1: "Repository or indexing error"},
        output_schema={
            "type": "object",
            "properties": {
                "branch": {"type": "string"},
                "task": {"type": "string"},
                "budget": {"type": "string"},
                "preamble": {"type": "string"},
                "tokens_estimated": {"type": "integer"},
            },
        },
        examples=("synap ctx", "synap ctx 'Add authentication' --budget dense", "synap ctx --json"),
        is_core_agent=True,
        slash_command="/ctx",
        slash_syntax="/ctx [task]",
    ),
    CommandDef(
        name="find",
        one_line_help="Execute a hybrid structural search across symbols, docs, and files.",
        description="Executes a 5-tier intent-routed hybrid search combining AST symbol graph traversal, FTS5 documentation full-text search, and Git commit history.",
        arguments=(
            ArgumentDef(
                name="query",
                description="Search query, symbol name, or path.",
                required=True,
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--summary/--full",),
                description="Return concise match summaries vs full text.",
                is_flag=True,
                default=True,
            ),
            OptionDef(
                flags=("--max-tokens", "-m"),
                description="Maximum token budget for returned context.",
                default=4000,
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Search completed successfully", 1: "Invalid query or repository error"},
        output_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "matches": {"type": "array"},
                "intent": {"type": "string"},
            },
        },
        examples=(
            "synap find AuthService",
            "synap find 'database pool' --summary",
            "synap find main.py --json",
        ),
        is_core_agent=True,
        slash_command="/find",
        slash_syntax="/find <query>",
        aliases=("search",),
    ),
    CommandDef(
        name="remember",
        one_line_help="Save an architectural decision, fact, or constraint into local persistent memory.",
        description="Saves an operational observation, environment fact, or architectural decision into local persistent SQLite memory (.synap/synap.db).",
        arguments=(
            ArgumentDef(
                name="key_or_content",
                description="Key and content, or single content string.",
                required=True,
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--summary", "-s"),
                description="One-line summary for rapid preamble inclusion.",
                default="",
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Memory recorded successfully", 1: "Storage write error"},
        output_schema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer"},
                "context_key": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        examples=(
            "synap remember auth_policy 'Use bcrypt with 12 rounds'",
            "synap remember db_pool 'Max pool size is 20'",
            "synap remember 'Connection timeout set to 5000ms' --json",
        ),
        is_core_agent=True,
        slash_command="/remember",
        slash_syntax="/remember <key> <content>",
    ),
    CommandDef(
        name="status",
        one_line_help="Show truthful status of repo, branch, daemon & symbols.",
        description="Displays the truthful status of git repository, active branch, background daemon lifecycle, indexed symbol counts, and SQLite WAL database health.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Status retrieved successfully", 1: "Repository error"},
        output_schema={
            "type": "object",
            "properties": {
                "is_repository": {"type": "boolean"},
                "branch": {"type": "string"},
                "daemon_running": {"type": "boolean"},
                "indexed_symbols": {"type": "integer"},
            },
        },
        examples=("synap status", "synap status --json"),
        is_core_agent=True,
        slash_command="/status",
        slash_syntax="/status",
    ),
    CommandDef(
        name="mcp",
        one_line_help="Model Context Protocol (MCP) server commands.",
        description="Provides Model Context Protocol stdio transport server and verification suite for IDE coding agents (Cursor, Windsurf, Claude Code, Cline).",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Success", 1: "Server or configuration error"},
        output_schema={
            "type": "object",
            "properties": {
                "tools": {"type": "array"},
                "status": {"type": "string"},
            },
        },
        examples=("synap mcp serve", "synap mcp verify", "synap mcp config"),
        is_core_agent=True,
        slash_command="/mcp",
        slash_syntax="/mcp [serve|verify|config]",
    ),
    CommandDef(
        name="bench",
        one_line_help="Run multi-repo Git-history grounding and token-efficiency benchmark.",
        description="Executes automated token efficiency and retrieval benchmark, comparing Synapse structural AST context packing against naive full-file reading baselines.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--output", "-o"),
                description="Output path for benchmark numbers JSON.",
                default="bench/numbers.json",
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Benchmark completed successfully", 1: "Benchmark error"},
        output_schema={
            "type": "object",
            "properties": {
                "queries_evaluated": {"type": "integer"},
                "recall_at_5": {"type": "number"},
                "recall_at_10": {"type": "number"},
                "mrr": {"type": "number"},
                "token_savings_percent": {"type": "number"},
            },
        },
        examples=("synap bench", "synap bench --output bench/numbers.json"),
        is_core_agent=True,
        slash_command="/bench",
        slash_syntax="/bench",
    ),
    CommandDef(
        name="stats",
        one_line_help="Show local cumulative token efficiency and avoided token metrics.",
        description="Tracks local cumulative usage without sending any telemetry: calls, tokens served, and estimated tokens avoided by using structural AST retrieval instead of raw file reads.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
            OptionDef(
                flags=("--reset",), description="Reset local stats.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Stats loaded successfully", 1: "Storage error"},
        output_schema={
            "type": "object",
            "properties": {
                "calls": {"type": "integer"},
                "tokens_served": {"type": "integer"},
                "estimated_tokens_avoided": {"type": "integer"},
                "estimation_method": {"type": "string"},
                "breakdown": {"type": "object"},
            },
        },
        examples=("synap stats", "synap stats --json", "synap stats --reset"),
        is_core_agent=True,
        slash_command="/stats",
        slash_syntax="/stats [--json] [--reset]",
    ),
    CommandDef(
        name="init",
        one_line_help="Initialize local Synap state and perform first scan.",
        description="Initializes .synap/ repository context storage, creates SQLite schema, configures settings, and performs initial AST symbol indexing.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to initialize.",
                required=False,
                default=".",
            ),
        ),
        options=(
            OptionDef(
                flags=("--skip-llm",),
                description="Skip local LLM checks during init.",
                is_flag=True,
                default=False,
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "Initialization succeeded", 1: "Initialization error"},
        output_schema={
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "path": {"type": "string"},
                "indexed_symbols": {"type": "integer"},
            },
        },
        examples=("synap init", "synap init --skip-llm", "synap init /path/to/repo"),
        is_core_agent=True,
        slash_command="/init",
        slash_syntax="/init",
    ),
    CommandDef(
        name="doctor",
        one_line_help="Validate environment and system health diagnostics.",
        description="Performs thorough system health check: Git repository state, Python version, dependencies, SQLite WAL database, daemon status, and disk space.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to inspect.",
                required=False,
                default=".",
            ),
        ),
        options=(
            OptionDef(
                flags=("--fix",),
                description="Attempt automatic remediation of degraded checks.",
                is_flag=True,
                default=False,
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "System healthy", 1: "Health check error or failure"},
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "checks": {"type": "array"},
                "fixes_applied": {"type": "array"},
            },
        },
        examples=("synap doctor", "synap doctor --fix", "synap doctor --json"),
        is_core_agent=True,
        slash_command="/doctor",
        slash_syntax="/doctor [--fix]",
        aliases=("doc",),
    ),
    CommandDef(
        name="selftest",
        one_line_help="Run end-to-end self-test suite verifying agent SKILL.md workflows.",
        description="Simulates the SKILL.md agent workflow end to end: startup preamble, context fetch (ctx), remember a decision, query symbols, and read skeleton on a fixture repository.",
        options=(
            OptionDef(
                flags=("--agent",),
                description="Run agent SKILL.md simulation workflow.",
                is_flag=True,
                default=True,
            ),
            OptionDef(
                flags=("--verbose", "-v"),
                description="Verbose step-by-step diagnostic output.",
                is_flag=True,
                default=False,
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        exit_codes={0: "All self-test stages passed", 1: "Self-test stage failed"},
        output_schema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "stages": {"type": "array"},
            },
        },
        examples=("synap selftest", "synap selftest --agent", "synap selftest --json"),
        is_core_agent=True,
        slash_command="/selftest",
        slash_syntax="/selftest [--agent]",
    ),
]

_OTHER_COMMANDS: list[CommandDef] = [
    CommandDef(
        name="forget",
        one_line_help="Remove memory item by key from local persistent memory.",
        description="Deletes a specific memory item by key from local persistent memory (.synap/synap.db).",
        arguments=(
            ArgumentDef(
                name="key",
                description="Memory key to remove.",
                required=True,
            ),
        ),
        options=(OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),),
        exit_codes={0: "Memory deleted", 1: "Memory key not found or database error"},
        examples=("synap forget db_timeout",),
        slash_command="/forget",
        slash_syntax="/forget <key>",
    ),
    CommandDef(
        name="search",
        one_line_help="Execute a hybrid structural search across the repository.",
        description="Executes a 5-tier intent-routed hybrid search across symbols, docs, and git commit history.",
        arguments=(
            ArgumentDef(
                name="query",
                description="Search query or symbol name.",
                required=True,
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--summary/--full",),
                description="Return concise match summaries vs full text.",
                is_flag=True,
                default=True,
            ),
            OptionDef(
                flags=("--max-tokens", "-m"),
                description="Maximum token budget.",
                default=4000,
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        aliases=("find",),
        examples=("synap search AuthService", "synap search 'database pool' --summary"),
    ),
    CommandDef(
        name="recall",
        one_line_help="Recall saved memories from local persistent memory.",
        description="Retrieves operational observations or architectural facts from persistent memory.",
        arguments=(
            ArgumentDef(
                name="key",
                description="Optional topic key filter.",
                required=False,
                default="",
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--limit", "-n"), description="Maximum entries to return.", default=10
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        examples=("synap recall", "synap recall auth_policy", "synap recall --json"),
    ),
    CommandDef(
        name="skeleton",
        one_line_help="Print the structural code skeleton of a file (stripping function/method bodies).",
        description="Extracts AST signatures, types, classes, and docstrings of a source file while stripping function and method bodies (85% token reduction).",
        arguments=(
            ArgumentDef(
                name="file_path",
                description="Path to file to skeletonize.",
                required=True,
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        aliases=("sk",),
        examples=("synap skeleton src/my_module.py", "synap sk src/auth/service.py"),
    ),
    CommandDef(
        name="outline",
        one_line_help="Print structural AST outline (functions, classes, methods, and line ranges) of a file.",
        description="Prints high-level structural outline of functions, classes, methods, and line ranges without implementation code.",
        arguments=(
            ArgumentDef(
                name="file_path",
                description="Path to file to outline.",
                required=True,
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        examples=("synap outline main.py",),
    ),
    CommandDef(
        name="explain",
        one_line_help="Explain a symbol's definition, callers, dependencies, and test coverage in the code graph.",
        description="Deep structural symbol inspection: definition, callers, dependencies, and impacted tests.",
        arguments=(
            ArgumentDef(
                name="symbol",
                description="Symbol or function name to explain.",
                required=True,
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        aliases=("ex",),
        examples=("synap explain my_function", "synap ex AuthService"),
    ),
    CommandDef(
        name="blast",
        one_line_help="Analyze blast radius of uncommitted changes (touched symbols, direct callers, and impacted tests).",
        description="Calculates impact radius of uncommitted git changes down to callers and test files.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        examples=("synap blast", "synap blast --json"),
    ),
    CommandDef(
        name="hubs",
        one_line_help="Discover top architectural hubs using Personalized PageRank over the code graph.",
        description="Ranks top architectural code hubs using graph centrality and Personalized PageRank.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(flags=("--limit", "-n"), description="Number of hubs to return.", default=10),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        examples=("synap hubs", "synap hubs --limit 5"),
    ),
    CommandDef(
        name="diff",
        one_line_help="Show raw unified git diff of uncommitted changes.",
        description="Displays git diff of uncommitted changes, staged or unstaged.",
        arguments=(
            ArgumentDef(
                name="file_path",
                description="Optional file path to diff.",
                required=False,
                default="",
            ),
        ),
        options=(OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),),
        examples=("synap diff", "synap diff main.py"),
    ),
    CommandDef(
        name="test",
        one_line_help="Run tests impacted by uncommitted changes using AST blast radius analysis.",
        description="Runs test suite filtered to tests impacted by uncommitted AST changes.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--dry-run",),
                description="Print recommended pytest command without running it.",
                is_flag=True,
                default=False,
            ),
        ),
        aliases=("t",),
        examples=("synap test", "synap test --dry-run"),
    ),
    CommandDef(
        name="pack",
        one_line_help="Pack token-budgeted repository context for LLM prompts.",
        description="Exports token-budgeted repository context pack with AST skeletons of hubs and dirty changes.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--max-tokens", "-m"),
                description="Maximum token budget.",
                default=8000,
            ),
            OptionDef(flags=("--output", "-o"), description="Output file path.", default=""),
        ),
        examples=("synap pack", "synap pack --max-tokens 4000"),
    ),
    CommandDef(
        name="rules",
        one_line_help="Generate universal agent directives for Cursor, Claude Code, and AGENTS.md.",
        description="Generates synchronized agent instruction rules (.cursorrules, CLAUDE.md, AGENTS.md).",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--target", "-t"),
                description="Target file (cursor, claude, agents, all).",
                default="all",
            ),
            OptionDef(
                flags=("--stdout",),
                description="Print rules to standard output.",
                is_flag=True,
                default=False,
            ),
        ),
        examples=("synap rules", "synap rules --stdout"),
    ),
    CommandDef(
        name="context",
        one_line_help="Print the session startup context preamble.",
        description="Prints token-bounded startup context preamble (< 750 tokens) containing branch, dirty files, hubs, and lessons.",
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        examples=("synap context", "synap context --json"),
    ),
    CommandDef(
        name="global",
        one_line_help="Inspect cross-project global developer habits and preferences (~/.synap/global_memory.db).",
        description="Queries cross-project global memory store for developer preferences, conventions, and habits.",
        arguments=(
            ArgumentDef(
                name="query",
                description="Optional search query.",
                required=False,
                default="",
            ),
        ),
        options=(
            OptionDef(
                flags=("--limit", "-n"), description="Maximum entries to return.", default=10
            ),
            OptionDef(
                flags=("--json",), description="Output as JSON.", is_flag=True, default=False
            ),
        ),
        examples=("synap global", "synap global python"),
        slash_command="/global",
        slash_syntax="/global [query]",
    ),
    CommandDef(
        name="ingest",
        one_line_help="Promote/clone a global memory from ~/.synap/global_memory.db into the local repository.",
        description="Promotes a global cross-project memory into the local repository's persistent context.",
        arguments=(
            ArgumentDef(
                name="global_id",
                description="Global memory ID or prefix to ingest.",
                required=True,
            ),
        ),
        options=(
            OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),
            OptionDef(
                flags=("--as-category", "-c"),
                description="Local category assignment.",
                default="note",
            ),
        ),
        examples=("synap ingest 1234abcd",),
        slash_command="/ingest",
        slash_syntax="/ingest <id>",
    ),
    CommandDef(
        name="wiki",
        one_line_help="Manage L2 Wiki Documentation.",
        description="Structural markdown wiki engine: generate, inspect, and preview 1:1 file documentation.",
        options=(OptionDef(flags=("--path", "-p"), description="Repository path.", default="."),),
        examples=("synap wiki status", "synap wiki generate", "synap wiki show index"),
        slash_command="/wiki",
        slash_syntax="/wiki [status|generate|show]",
    ),
    CommandDef(
        name="logs",
        one_line_help="View and tail Synap runtime logs.",
        description="Displays recent background daemon and runtime activity logs.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path.",
                required=False,
                default=".",
            ),
        ),
        options=(
            OptionDef(flags=("--lines", "-n"), description="Number of lines to view.", default=50),
            OptionDef(
                flags=("--follow", "-f"),
                description="Follow log output continuously.",
                is_flag=True,
                default=False,
            ),
        ),
        examples=("synap logs", "synap logs -n 100", "synap logs -f"),
        slash_command="/logs",
        slash_syntax="/logs [-n <lines>]",
    ),
    CommandDef(
        name="setup",
        one_line_help="Interactive first-run setup and onboarding.",
        description="Guides first-time users through LLM provider selection, API keys, and repository indexing.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap setup",),
    ),
    CommandDef(
        name="install",
        one_line_help="Seamless 1-command installer: discovers IDEs, registers Synap MCP server globally, and initializes repository.",
        description="Discovers installed IDEs (Cursor, Windsurf, Claude Code, Cline), configures MCP endpoints, installs Git hooks, and initializes the repository.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path.",
                required=False,
                default=".",
            ),
        ),
        options=(
            OptionDef(flags=("--ide",), description="Specific IDE target.", default="all"),
            OptionDef(
                flags=("--global", "-g"),
                description="Install MCP server into global user configuration.",
                is_flag=True,
                default=False,
            ),
            OptionDef(
                flags=("--local", "-l"),
                description="Install MCP server into local repository only.",
                is_flag=True,
                default=False,
            ),
        ),
        examples=("synap install", "synap install --ide cursor --local"),
    ),
    CommandDef(
        name="uninstall",
        one_line_help="Uninstall the Synap CLI package.",
        description="Removes Synapse MCP configuration from IDEs and uninstalls local package.",
        options=(
            OptionDef(
                flags=("--yes", "-y"),
                description="Confirm uninstall without prompting.",
                is_flag=True,
                default=False,
            ),
        ),
        examples=("synap uninstall", "synap uninstall -y"),
    ),
    CommandDef(
        name="update",
        one_line_help="Check for updates and upgrade the Synap runtime.",
        description="Checks for updates to the synap-git package and upgrades the runtime.",
        options=(
            OptionDef(
                flags=("--force", "-f"),
                description="Force upgrade even if up-to-date.",
                is_flag=True,
                default=False,
            ),
        ),
        examples=("synap update",),
    ),
    CommandDef(
        name="version",
        one_line_help="Print the Synap package version.",
        description="Outputs the active installed Synap package version.",
        examples=("synap version",),
    ),
    CommandDef(
        name="index",
        one_line_help="Index and map code symbols, caller/callee relationships, and embeddings into the local database.",
        description="Full AST scan and indexing of the repository into SQLite WAL database.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to index.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap index",),
    ),
    CommandDef(
        name="sync",
        one_line_help="Synchronize database index with latest Git state and working tree changes.",
        description="Incrementally updates SQLite index based on changed git files.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to synchronize.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap sync",),
    ),
    CommandDef(
        name="wipe",
        one_line_help="Completely purge the local index for a fresh rebuild.",
        description="Deletes and clears all local index tables for a clean rebuild.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to wipe.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap wipe",),
    ),
    CommandDef(
        name="start",
        one_line_help="Start the Synap daemon in the background.",
        description="Starts background file-watching daemon process.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to watch.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap start",),
    ),
    CommandDef(
        name="stop",
        one_line_help="Gracefully terminate background services.",
        description="Sends termination signal to background watcher daemon and cleans up locks.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to stop.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap stop",),
    ),
    CommandDef(
        name="restart",
        one_line_help="Restart background daemon services.",
        description="Stops running daemon and restarts it freshly.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path to restart.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap restart",),
    ),
    CommandDef(
        name="rollback",
        one_line_help="Rollback active state to a previous commit.",
        description="Reverts git working tree and Synapse index to a specified commit.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap rollback",),
    ),
    CommandDef(
        name="repair",
        one_line_help="Repair a broken index state.",
        description="Reconstructs damaged SQLite graph tables and clears stale lock files.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap repair",),
    ),
    CommandDef(
        name="ui",
        one_line_help="Open the Synap diagnostic UI in your browser.",
        description="Launches local FastAPI server and opens Web UI dashboard in the browser.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap ui",),
    ),
    CommandDef(
        name="cost",
        one_line_help="Show detailed LLM call, token usage, and estimated USD cost metrics.",
        description="Displays table of external LLM API token calls and calculated costs.",
        arguments=(
            ArgumentDef(
                name="path",
                description="Repository path.",
                required=False,
                default=".",
            ),
        ),
        examples=("synap cost",),
    ),
    CommandDef(
        name="checkpoint",
        one_line_help="Manage Context Checkpoints.",
        description="Creates, lists, or restores agent thought-process checkpoints.",
        examples=("synap checkpoint list", "synap checkpoint create --doing 'Refactoring'"),
    ),
    CommandDef(
        name="daemon",
        one_line_help="Manage background daemon services.",
        description="Inspects daemon heartbeat and controls background service.",
        examples=("synap daemon status",),
    ),
    CommandDef(
        name="memory",
        one_line_help="Manage L3 Agent Memory.",
        description="Inspect, list, and verify L3 working memory entries.",
        examples=("synap memory list", "synap memory status"),
    ),
    CommandDef(
        name="lessons",
        one_line_help="Manage Agent Lessons.",
        description="Lists and approves negative constraint lessons learned from git reverts.",
        examples=("synap lessons list", "synap lessons approve 1"),
    ),
    CommandDef(
        name="usage",
        one_line_help="View AI Usage Tracking.",
        description="Displays AI model usage statistics.",
        examples=("synap usage show",),
    ),
    CommandDef(
        name="hooks",
        one_line_help="Manage Git hooks for zero-daemon reindexing.",
        description="Installs or removes post-commit Git hooks for zero-daemon reindexing.",
        examples=("synap hooks install", "synap hooks uninstall"),
    ),
]

# TUI-only virtual slash commands
_TUI_SPECIAL_COMMANDS: list[tuple[str, str, str]] = [
    ("/model", "/model [probe|set <m>]", "Auto-discover active runtimes or set model override"),
    ("/skill", "/skill [sync|export]", "Synchronize or export agent SKILL.md and rules"),
    ("/help", "/help", "Show concise slash-command cheatsheet"),
    ("/quit", "/quit or /exit", "Exit the interactive REPL"),
]


# Build internal registries
COMMAND_REGISTRY: dict[str, CommandDef] = {c.name: c for c in _CORE_COMMANDS + _OTHER_COMMANDS}

# Add alias mappings
for c in _CORE_COMMANDS + _OTHER_COMMANDS:
    for alias in c.aliases:
        COMMAND_REGISTRY.setdefault(alias, c)


def get_command(name: str) -> CommandDef | None:
    """Retrieve command definition by canonical name or alias."""
    return COMMAND_REGISTRY.get(name)


def get_all_commands() -> list[CommandDef]:
    """Return all unique command definitions in the registry."""
    seen: set[str] = set()
    result: list[CommandDef] = []
    for cmd in list(_CORE_COMMANDS) + list(_OTHER_COMMANDS):
        if cmd.name not in seen:
            seen.add(cmd.name)
            result.append(cmd)
    return result


def get_core_agent_commands() -> list[CommandDef]:
    """Return core agent commands."""
    return [c for c in _CORE_COMMANDS if c.is_core_agent]


def get_slash_commands() -> list[tuple[str, str, str]]:
    """Return list of (slash_cmd, syntax, description) for all slash-capable commands."""
    items: list[tuple[str, str, str]] = []
    # Core commands first
    for cmd in _CORE_COMMANDS:
        if cmd.slash_command:
            syntax = cmd.slash_syntax or cmd.slash_command
            items.append((cmd.slash_command, syntax, cmd.one_line_help))
    # Other commands that have slash representation
    for cmd in _OTHER_COMMANDS:
        if cmd.slash_command:
            syntax = cmd.slash_syntax or cmd.slash_command
            items.append((cmd.slash_command, syntax, cmd.one_line_help))
    # TUI special commands
    for slash_cmd, syntax, desc in _TUI_SPECIAL_COMMANDS:
        items.append((slash_cmd, syntax, desc))
    return items


def generate_tui_slash_commands() -> list[tuple[str, str]]:
    """Generate autocompletion list for prompt_toolkit in tui.py.

    Format: list of (slash_command, hint_with_syntax).
    """
    results: list[tuple[str, str]] = []
    for slash_cmd, syntax, desc in get_slash_commands():
        hint = syntax[len(slash_cmd) :].strip()
        if hint:
            results.append((slash_cmd, f"{hint} {desc}"))
        else:
            results.append((slash_cmd, desc))
    return results


def generate_help_markdown() -> str:
    """Generate markdown command reference table for README.md."""
    lines: list[str] = [
        "## Command Reference",
        "",
        "Synapse provides a unified set of CLI and REPL commands for AI coding agents and human engineers:",
        "",
        "### Core Agent Commands",
        "",
        "| Command | Syntax | Description | Example |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for cmd in get_core_agent_commands():
        syntax = cmd.slash_syntax or f"synap {cmd.name}"
        example = cmd.examples[0] if cmd.examples else f"synap {cmd.name}"
        lines.append(f"| `{cmd.name}` | `{syntax}` | {cmd.one_line_help} | `{example}` |")

    lines.extend(
        [
            "",
            "### Auxiliary & Management Commands",
            "",
            "| Command | Description |",
            "| :--- | :--- |",
        ]
    )
    for cmd in _OTHER_COMMANDS:
        lines.append(f"| `synap {cmd.name}` | {cmd.one_line_help} |")

    return "\n".join(lines)


def generate_skill_commands_markdown() -> str:
    """Generate concise command reference section for SKILL.md embedding."""
    lines: list[str] = [
        "### Essential Synapse Commands",
        "",
        "| Command | Purpose | Token Impact |",
        "| :--- | :--- | :--- |",
        "| `synap ctx [task]` | High-density startup context preamble | < 750 tokens |",
        "| `synap find <query>` | Intent-routed symbol & doc search | Summary-only saves 85% |",
        "| `synap skeleton <file>` | Extract signatures, types, docstrings | 80-90% token reduction |",
        "| `synap remember <k> <v>` | Save architectural decisions/facts | Permanent WAL memory |",
        "| `synap stats` | Cumulative token efficiency metrics | Local zero-telemetry |",
        "| `synap doctor` | Health check & auto-remediation | Diagnostics |",
        "| `synap selftest --agent` | Verify agent workflow end-to-end | Verification |",
    ]
    return "\n".join(lines)
