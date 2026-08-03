"use client"

import React, { useState } from "react"
import {
  Cpu,
  GitBranch,
  Database,
  Server,
  CheckCircle2
} from "lucide-react"

interface ArchitectureComponent {
  id: string
  module: string
  name: string
  category: "interface" | "core" | "storage" | "worker"
  description: string
  techDetails: string
  inputData: string
  outputData: string
  fileLocation: string
}

const ARCH_COMPONENTS: ArchitectureComponent[] = [
  {
    id: "cli",
    module: "synap_git.cli",
    name: "Typer CLI Interface",
    category: "interface",
    description: "Command line entrypoint managing runtime daemons, setup onboarding, and doctor diagnostics.",
    techDetails: "Built with Typer & Rich. Mounts subcommands setup, start, stop, status, doctor, search, wiki, mcp.",
    inputData: "User CLI args & repository flag",
    outputData: "JSON / Human formatted stdout & daemon controls",
    fileLocation: "src/synap_git/cli/main.py"
  },
  {
    id: "daemon",
    module: "synap_git.indexer.daemon",
    name: "Runtime Daemon Process",
    category: "core",
    description: "Asynchronous background process hosting the Git commit watcher loop, Uvicorn API server, and wiki worker queue.",
    techDetails: "Asyncio event loop with SIGINT/SIGTERM signal handlers. Manages .synap/daemon.pid lockfile.",
    inputData: "Git repository filesystem polling (every 2s)",
    outputData: "Background index refreshes & worker tasks",
    fileLocation: "src/synap_git/indexer/daemon.py"
  },
  {
    id: "git_state",
    module: "synap_git.git.state",
    name: "Git OID Delta Engine",
    category: "core",
    description: "Detects active commit shifts, branch checkouts, merges, and reverts via raw Git subprocess calls.",
    techDetails: "Uses git diff-tree to compute file deltas without scanning unchanged filesystem trees.",
    inputData: "Local .git HEAD pointer & working tree",
    outputData: "Commit OIDs, untracked changes, diff deltas",
    fileLocation: "src/synap_git/git/state.py"
  },
  {
    id: "indexer_engine",
    module: "synap_git.indexer.engine",
    name: "Parallel Indexer Engine",
    category: "core",
    description: "Orchestrates multi-threaded file reading, Tree-sitter AST symbol parsing, and database transactions.",
    techDetails: "SynapRuntime coordinates AST traversal and SQLite WAL bulk upserts inside isolated transactions.",
    inputData: "Modified code files & diff deltas",
    outputData: "Symbol graph nodes & dependency edges",
    fileLocation: "src/synap_git/indexer/engine.py"
  },
  {
    id: "parser_registry",
    module: "synap_git.parser.registry",
    name: "Tree-sitter Parser Registry",
    category: "core",
    description: "High-fidelity AST symbol parser extracting functions, classes, methods, and import dependency edges.",
    techDetails: "Tree-sitter bindings supporting Python, TypeScript, JavaScript, Rust, Go, C++, Java, C#.",
    inputData: "Raw source code AST grammar nodes",
    outputData: "SHA256 content-hashed symbols & edges",
    fileLocation: "src/synap_git/parser/registry.py"
  },
  {
    id: "sqlite_storage",
    module: "synap_git.storage.sqlite",
    name: "SQLite Engine (WAL + FTS5)",
    category: "storage",
    description: "Single-file local relational database persisting structural code graphs, FTS5 lexical indexes, and L3 memories.",
    techDetails: "PRAGMA journal_mode=WAL & synchronous=NORMAL. Supports SQLite Recursive CTE graph traversals.",
    inputData: "Parsed AST symbols, dependency edges & memories",
    outputData: ".synap/synap.db relational tables",
    fileLocation: "src/synap_git/storage/sqlite.py"
  },
  {
    id: "wiki_worker",
    module: "synap_git.indexer.wiki",
    name: "Async Semantic Wiki Worker",
    category: "worker",
    description: "Generates asynchronous markdown summaries of files and modules stored under .synap/wiki/.",
    techDetails: "Listens to background wiki_queue. Updates status from 'stale' to 'fresh' asynchronously.",
    inputData: "Modified file contents & symbol schemas",
    outputData: "Markdown documentation summaries under .synap/wiki/",
    fileLocation: "src/synap_git/indexer/wiki.py"
  },
  {
    id: "retrieval_engine",
    module: "synap_git.retrieval.engine",
    name: "Hybrid Retrieval Engine",
    category: "core",
    description: "Combines FTS5 keyword matching with SQLite CTE graph expansion and tiktoken context budget enforcement.",
    techDetails: "4-stage pipeline: Filter -> CTE Expansion -> FTS5 Match -> Ranking & Token Budgeting.",
    inputData: "Agent query string & max_tokens budget (e.g. 4000)",
    outputData: "Token-bounded structural context package",
    fileLocation: "src/synap_git/retrieval/engine.py"
  },
  {
    id: "mcp_server",
    module: "synap_git.mcp.server",
    name: "FastMCP Stdio Server",
    category: "interface",
    description: "Serves Model Context Protocol (MCP) commands over stdio to AI agents (Cursor, Windsurf, Claude, Antigravity).",
    techDetails: "Exposes synap_search, synap_create_checkpoint, synap_log_decision, synap_get_approved_memory.",
    inputData: "Agent JSON-RPC tool calls over stdio",
    outputData: "Structured context packages & memory IDs",
    fileLocation: "src/synap_git/mcp/server.py"
  }
]

export function ArchitectureDiagram() {
  const [selectedId, setSelectedId] = useState<string>("indexer_engine")
  const selectedComp = ARCH_COMPONENTS.find(c => c.id === selectedId) || ARCH_COMPONENTS[3]

  return (
    <section id="architecture" className="py-20 bg-slate-950 border-b border-slate-800/80 relative">

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-xs font-mono text-blue-400 mb-3">
            <Cpu className="w-3.5 h-3.5" />
            <span>High-Level Design (HLD)</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-bold text-slate-50 tracking-tight">
            Built as a Pure Projection Engine
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg font-sans">
            Synapse does not synthesize code structure using AI; it extracts it deterministically using
            <strong className="text-slate-200"> Tree-sitter parsers</strong> and <strong className="text-slate-200">Recursive SQL CTE traversals</strong>.
          </p>
        </div>

        {/* Component Topology Map */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">

          {/* HLD Interactive Grid (Left 7 Cols) */}
          <div className="lg:col-span-7 space-y-6">

            {/* Top Ingestion Flow Card */}
            <div className="glass-card rounded-2xl p-5 border border-slate-800">
              <div className="flex items-center justify-between text-xs font-mono text-slate-400 mb-4 pb-2 border-b border-slate-800/60">
                <span className="flex items-center gap-1.5 text-blue-400 font-semibold">
                  <GitBranch className="w-4 h-4" /> 1. Ingestion Pipeline & Git State Engine
                </span>
                <span className="text-slate-500">HEAD OID Projection</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {ARCH_COMPONENTS.filter(c => ["git_state", "parser_registry", "indexer_engine"].includes(c.id)).map(comp => (
                  <button
                    key={comp.id}
                    onClick={() => setSelectedId(comp.id)}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      selectedId === comp.id
                        ? "bg-blue-950/60 border-blue-500 text-slate-100 ring-1 ring-blue-500/50 shadow-lg shadow-blue-500/10"
                        : "bg-slate-900/60 border-slate-800 text-slate-300 hover:border-slate-700 hover:bg-slate-850"
                    }`}
                  >
                    <div className="text-[10px] font-mono text-blue-400 mb-1">{comp.module}</div>
                    <div className="text-xs font-mono font-semibold truncate">{comp.name}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Middle Storage & Worker Flow Card */}
            <div className="glass-card rounded-2xl p-5 border border-slate-800">
              <div className="flex items-center justify-between text-xs font-mono text-slate-400 mb-4 pb-2 border-b border-slate-800/60">
                <span className="flex items-center gap-1.5 text-emerald-400 font-semibold">
                  <Database className="w-4 h-4" /> 2. Storage & Async Documentation Engine
                </span>
                <span className="text-slate-500">SQLite WAL + FTS5</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {ARCH_COMPONENTS.filter(c => ["sqlite_storage", "wiki_worker", "retrieval_engine"].includes(c.id)).map(comp => (
                  <button
                    key={comp.id}
                    onClick={() => setSelectedId(comp.id)}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      selectedId === comp.id
                        ? "bg-emerald-950/60 border-emerald-500 text-slate-100 ring-1 ring-emerald-500/50 shadow-lg shadow-emerald-500/10"
                        : "bg-slate-900/60 border-slate-800 text-slate-300 hover:border-slate-700 hover:bg-slate-850"
                    }`}
                  >
                    <div className="text-[10px] font-mono text-emerald-400 mb-1">{comp.module}</div>
                    <div className="text-xs font-mono font-semibold truncate">{comp.name}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Bottom Interface & MCP Protocol Flow Card */}
            <div className="glass-card rounded-2xl p-5 border border-slate-800">
              <div className="flex items-center justify-between text-xs font-mono text-slate-400 mb-4 pb-2 border-b border-slate-800/60">
                <span className="flex items-center gap-1.5 text-purple-400 font-semibold">
                  <Server className="w-4 h-4" /> 3. Agent Interfaces & Stdio Protocol
                </span>
                <span className="text-slate-500">FastMCP Stdio Server</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {ARCH_COMPONENTS.filter(c => ["cli", "daemon", "mcp_server"].includes(c.id)).map(comp => (
                  <button
                    key={comp.id}
                    onClick={() => setSelectedId(comp.id)}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      selectedId === comp.id
                        ? "bg-purple-950/60 border-purple-500 text-slate-100 ring-1 ring-purple-500/50 shadow-lg shadow-purple-500/10"
                        : "bg-slate-900/60 border-slate-800 text-slate-300 hover:border-slate-700 hover:bg-slate-850"
                    }`}
                  >
                    <div className="text-[10px] font-mono text-purple-400 mb-1">{comp.module}</div>
                    <div className="text-xs font-mono font-semibold truncate">{comp.name}</div>
                  </button>
                ))}
              </div>
            </div>

          </div>

          {/* Component Deep Inspector Panel (Right 5 Cols) */}
          <div className="lg:col-span-5 glass-card rounded-2xl p-6 border border-slate-800 min-h-[440px] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div>
                  <span className="text-[10px] font-mono text-blue-400 uppercase tracking-widest">{selectedComp.module}</span>
                  <h3 className="text-xl font-mono font-bold text-slate-100 mt-0.5">{selectedComp.name}</h3>
                </div>
                <span className="px-2.5 py-1 bg-slate-800 text-slate-300 text-xs font-mono rounded-lg border border-slate-700">
                  {selectedComp.category}
                </span>
              </div>

              <p className="mt-4 text-sm text-slate-300 font-sans leading-relaxed">
                {selectedComp.description}
              </p>

              {/* Technical Specifications */}
              <div className="mt-6 space-y-3 font-mono text-xs">
                <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800/80">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Architecture Implementation</div>
                  <div className="text-slate-200">{selectedComp.techDetails}</div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800/80">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Input Stream</div>
                    <div className="text-cyan-400 truncate">{selectedComp.inputData}</div>
                  </div>
                  <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800/80">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Output Stream</div>
                    <div className="text-emerald-400 truncate">{selectedComp.outputData}</div>
                  </div>
                </div>

                <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800/80 flex items-center justify-between">
                  <span className="text-slate-500 text-[10px]">Source File:</span>
                  <span className="text-slate-300">{selectedComp.fileLocation}</span>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono text-slate-400">
              <span className="flex items-center gap-1.5 text-blue-400">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Grounded in synap_git
              </span>
              <span className="text-slate-500">Pure Python 3.12+</span>
            </div>

          </div>

        </div>

      </div>

    </section>
  )
}
