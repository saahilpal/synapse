"use client"

import React, { useState } from "react"
import { motion } from "framer-motion"
import {
  Cpu,
  GitBranch,
  Database,
  Server,
  CheckCircle2,
  Code2,
  FileText,
  Brain,
  Zap,
  Layers,
  ArrowRight
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
    name: "Typer CLI & Commands",
    category: "interface",
    description: "Command line entrypoint managing daemons, full indexation, doctor health checks, and live status monitoring.",
    techDetails: "Built with Typer & Rich. Subcommands: init, index, sync, search, status --watch, doctor, wiki, mcp.",
    inputData: "User CLI flags & target repository path",
    outputData: "JSON / Terminal UI stdout & background daemon control",
    fileLocation: "src/synap_git/cli/main.py"
  },
  {
    id: "mcp",
    module: "synap_git.mcp.server",
    name: "FastMCP Stdio Server",
    category: "interface",
    description: "Low-latency Model Context Protocol bridge communicating directly with AI agent editors via standard I/O.",
    techDetails: "Exposes search, log_decision, get_context, checkpoint tools with sub-10ms intent routing.",
    inputData: "MCP JSON-RPC agent tool calls",
    outputData: "Grounded structural AST symbols & markdown context",
    fileLocation: "src/synap_git/mcp/server.py"
  },
  {
    id: "git_state",
    module: "synap_git.git.state",
    name: "Git State Fingerprinter",
    category: "core",
    description: "Detects commit shifts, branch checkouts, and uncommitted edits via mtime fingerprinting with zero latency.",
    techDetails: "Checks .git/HEAD, .git/index, and .git/refs timestamps. Subprocess fallback only on invalidation.",
    inputData: "Local .git HEAD & index timestamps",
    outputData: "GitState (OID, branch, dirty, change kind)",
    fileLocation: "src/synap_git/git/state.py"
  },
  {
    id: "parser_registry",
    module: "synap_git.parser.registry",
    name: "Tree-sitter Parser Registry",
    category: "core",
    description: "High-fidelity AST symbol parser extracting functions, classes, methods, and import dependency edges.",
    techDetails: "Native Tree-sitter grammars: Python, TypeScript, JavaScript, Rust, Go, C, C++, Java, Kotlin, Swift.",
    inputData: "Raw source code AST grammar nodes",
    outputData: "Deterministic SHA256 content-hashed symbols & edges",
    fileLocation: "src/synap_git/parser/registry.py"
  },
  {
    id: "sqlite_storage",
    module: "synap_git.storage.sqlite",
    name: "SQLite Storage (WAL + FTS5)",
    category: "storage",
    description: "Single-file local relational database persisting structural code graphs, FTS5 lexical indexes, and vector embeddings.",
    techDetails: "PRAGMA journal_mode=WAL & synchronous=NORMAL. Supports SQLite Recursive CTE graph traversals & LRU vector cache.",
    inputData: "Parsed AST symbols, dependency edges, vector arrays",
    outputData: ".synap/synap.db relational tables",
    fileLocation: "src/synap_git/storage/sqlite.py"
  },
  {
    id: "wiki_worker",
    module: "synap_git.indexer.wiki",
    name: "Async Semantic Wiki Worker",
    category: "worker",
    description: "Generates asynchronous markdown summaries of files and modules stored under .synap/wiki/.",
    techDetails: "Listens to background wiki_queue. Updates status from 'stale' to 'fresh' asynchronously using local or remote LLMs.",
    inputData: "Modified file contents & symbol schemas",
    outputData: "Markdown documentation summaries under .synap/wiki/",
    fileLocation: "src/synap_git/indexer/wiki.py"
  }
]

export function ArchitectureDiagram() {
  const [selectedComp, setSelectedComp] = useState<ArchitectureComponent>(ARCH_COMPONENTS[0])

  return (
    <section id="architecture" className="py-20 border-b border-border-subtle bg-[#090A0F]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="max-w-3xl mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-text-secondary text-xs font-mono mb-4">
            <Layers className="w-3.5 h-3.5 text-accent-blue" />
            <span>High-Level Design & Topology</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary tracking-tight">
            Designed for Instant Local Execution.
          </h2>
          <p className="mt-3 text-text-secondary font-sans text-sm sm:text-base leading-relaxed">
            Synapse runs as a lightweight, zero-dependency local daemon. It couples Tree-sitter AST parsers with SQLite WAL concurrency, delivering microsecond graph queries to AI agents without bogging down your machine.
          </p>
        </div>

        {/* Architecture Pipeline Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">

          {/* Component Selection Cards */}
          <div className="lg:col-span-6 grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-xs">
            {ARCH_COMPONENTS.map(comp => (
              <button
                key={comp.id}
                onClick={() => setSelectedComp(comp)}
                className={`p-4 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                  selectedComp.id === comp.id
                    ? "bg-surface-hover border-accent-blue/50 text-text-primary shadow-md"
                    : "bg-surface/60 border-border text-text-secondary hover:border-border-strong hover:bg-surface"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] uppercase font-bold text-text-muted">
                      {comp.category}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-subtle border border-border text-text-muted">
                      {comp.module.split(".").pop()}
                    </span>
                  </div>
                  <div className="font-semibold text-text-primary text-sm">
                    {comp.name}
                  </div>
                </div>
                <div className="mt-3 text-[11px] text-text-muted truncate">
                  {comp.fileLocation}
                </div>
              </button>
            ))}
          </div>

          {/* Detailed Inspector Panel */}
          <div className="lg:col-span-6 minimal-card p-6 flex flex-col justify-between font-mono text-xs">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-border">
                <div className="flex items-center gap-2.5">
                  <div className="h-7 w-7 rounded-lg bg-surface border border-border flex items-center justify-center">
                    <Cpu className="w-3.5 h-3.5 text-accent-blue" />
                  </div>
                  <div>
                    <span className="font-bold text-text-primary text-sm">{selectedComp.name}</span>
                    <span className="text-[11px] text-text-muted block">{selectedComp.module}</span>
                  </div>
                </div>
                <span className="text-[11px] text-accent-emerald bg-accent-emerald/10 px-2 py-0.5 rounded border border-accent-emerald/20">
                  Active in v2.4.0
                </span>
              </div>

              <div className="mt-5 space-y-4">
                <div>
                  <span className="text-text-muted block text-[11px] uppercase tracking-wider">Functional Role</span>
                  <p className="text-text-secondary mt-1 font-sans text-xs sm:text-sm leading-relaxed">
                    {selectedComp.description}
                  </p>
                </div>

                <div>
                  <span className="text-text-muted block text-[11px] uppercase tracking-wider">Implementation Mechanics</span>
                  <p className="text-text-secondary mt-1 font-sans text-xs sm:text-sm leading-relaxed">
                    {selectedComp.techDetails}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div className="p-3 rounded-lg bg-[#08090D] border border-border">
                    <span className="text-text-muted block text-[10px] uppercase">Input Stream</span>
                    <span className="text-text-secondary mt-1 block text-[11px] font-sans">
                      {selectedComp.inputData}
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-[#08090D] border border-border">
                    <span className="text-text-muted block text-[10px] uppercase">Output Payload</span>
                    <span className="text-text-secondary mt-1 block text-[11px] font-sans">
                      {selectedComp.outputData}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-border flex items-center justify-between text-text-muted text-[11px]">
              <span>Source: <code className="text-text-primary">{selectedComp.fileLocation}</code></span>
              <span className="text-accent-blue flex items-center gap-1">
                Zero Blocking I/O <CheckCircle2 className="w-3.5 h-3.5 text-accent-emerald" />
              </span>
            </div>
          </div>

        </div>

      </div>
    </section>
  )
}
