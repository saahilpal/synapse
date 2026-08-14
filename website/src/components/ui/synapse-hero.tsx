"use client"

import React, { useState } from "react"
import { motion } from "framer-motion"
import {
  Terminal,
  Cpu,
  GitBranch,
  Zap,
  Copy,
  Check,
  ArrowRight,
  ShieldCheck,
  Layers,
  Database,
  Search,
  GitCommit,
  RefreshCw,
  Code2,
  Lock,
  Box
} from "lucide-react"

interface GraphNode {
  id: string
  name: string
  type: "class" | "function" | "table" | "wiki"
  layer: "L1" | "L2" | "L3"
  connections: string[]
  tokens: number
  file: string
  detail: string
}

const GRAPH_NODES: GraphNode[] = [
  {
    id: "node-1",
    name: "SynapRuntime",
    type: "class",
    layer: "L1",
    connections: ["node-2", "node-4"],
    tokens: 180,
    file: "src/synap_git/indexer/engine.py",
    detail: "Core AST orchestrator & Tree-sitter coordinator"
  },
  {
    id: "node-2",
    name: "query_hybrid()",
    type: "function",
    layer: "L1",
    connections: ["node-3", "node-5"],
    tokens: 140,
    file: "src/synap_git/retrieval/engine.py",
    detail: "Deterministic sub-10ms intent & symbol resolver"
  },
  {
    id: "node-3",
    name: "sqlite_vec (WAL)",
    type: "table",
    layer: "L1",
    connections: [],
    tokens: 310,
    file: ".synap/synap.db",
    detail: "Cosine similarity with precalculated Euclidean norms"
  },
  {
    id: "node-4",
    name: "GitStateWatcher",
    type: "class",
    layer: "L1",
    connections: ["node-6"],
    tokens: 165,
    file: "src/synap_git/git/state.py",
    detail: "Filesystem mtime fingerprint invalidation"
  },
  {
    id: "node-5",
    name: "WikiEngine",
    type: "wiki",
    layer: "L2",
    connections: [],
    tokens: 220,
    file: ".synap/wiki/overview.md",
    detail: "Git-synced markdown architectural digests"
  },
  {
    id: "node-6",
    name: "BehavioralMemory",
    type: "class",
    layer: "L3",
    connections: [],
    tokens: 195,
    file: ".synap/synap.db:lessons",
    detail: "Revert lessons, checkpoints, & active constraints"
  }
]

export function SynapseHero() {
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null)
  const [installMethod, setInstallMethod] = useState<"pip" | "uv" | "cli">("pip")
  const [activeBranch, setActiveBranch] = useState("main")
  const [isSimulating, setIsSimulating] = useState(false)
  const [selectedNode, setSelectedNode] = useState<GraphNode>(GRAPH_NODES[0])
  const [activeView, setActiveView] = useState<"graph" | "mcp" | "savings">("graph")

  const copyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedCmd(id)
    setTimeout(() => setCopiedCmd(null), 2000)
  }

  const simulateBranchChange = () => {
    setIsSimulating(true)
    setTimeout(() => {
      setActiveBranch(prev => prev === "main" ? "feature/ast-vector-cache" : "main")
      setIsSimulating(false)
    }, 450)
  }

  const getCommand = () => {
    switch (installMethod) {
      case "pip": return "pip install synap-git"
      case "uv": return "uv tool install synap-git"
      case "cli": return "synap init && synap start"
    }
  }

  return (
    <section className="relative pt-12 pb-20 md:pt-20 md:pb-28 border-b border-border-subtle bg-grid-pattern subtle-glow">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">

        {/* Status Pill Badge */}
        <div className="flex justify-center mb-8">
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-surface border border-border text-xs font-mono text-text-secondary shadow-sm hover:border-border-strong transition-all cursor-pointer"
            onClick={simulateBranchChange}
          >
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-emerald opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-emerald"></span>
            </span>
            <span className="text-text-muted">Git OID Track:</span>
            <span className="text-accent-emerald font-medium flex items-center gap-1">
              <GitCommit className="w-3 h-3" /> {activeBranch}
            </span>
            <span className="text-border">|</span>
            <span className="text-accent-blue flex items-center gap-1 hover:underline">
              <RefreshCw className={`w-3 h-3 ${isSimulating ? "animate-spin" : ""}`} />
              Simulate Commit (9.2ms)
            </span>
          </motion.div>
        </div>

        {/* Hero Title & Value Proposition */}
        <div className="text-center max-w-4xl mx-auto">
          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.1 }}
            className="text-4xl sm:text-6xl lg:text-7xl font-display font-bold tracking-tight text-text-primary leading-[1.08]"
          >
            Git-Aware Structural Context for AI Coding Agents.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.2 }}
            className="mt-6 text-base sm:text-lg text-text-secondary max-w-2xl mx-auto font-sans leading-relaxed"
          >
            Maps your repository into a local SQLite Tree-sitter graph, asynchronous semantic wiki, and long-term behavioral memory. Zero cloud lock-in. Sub-10ms FastMCP retrieval for Cursor, Claude Code, and Windsurf.
          </motion.p>

          {/* Interactive Install Box */}
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.3 }}
            className="mt-8 flex flex-col items-center gap-3"
          >
            {/* Install Method Switcher */}
            <div className="flex items-center p-1 rounded-lg bg-surface border border-border text-xs font-mono">
              <button
                onClick={() => setInstallMethod("pip")}
                className={`px-3 py-1 rounded-md transition-all ${installMethod === "pip" ? "bg-text-primary text-background font-medium" : "text-text-muted hover:text-text-primary"}`}
              >
                pip
              </button>
              <button
                onClick={() => setInstallMethod("uv")}
                className={`px-3 py-1 rounded-md transition-all ${installMethod === "uv" ? "bg-text-primary text-background font-medium" : "text-text-muted hover:text-text-primary"}`}
              >
                uv tool
              </button>
              <button
                onClick={() => setInstallMethod("cli")}
                className={`px-3 py-1 rounded-md transition-all ${installMethod === "cli" ? "bg-text-primary text-background font-medium" : "text-text-muted hover:text-text-primary"}`}
              >
                quickstart
              </button>
            </div>

            {/* Command Bar */}
            <div className="flex items-center gap-3 bg-surface border border-border rounded-xl px-4 py-2.5 shadow-lg w-full max-w-md justify-between group hover:border-border-strong transition-all">
              <div className="flex items-center gap-2.5 font-mono text-xs text-text-primary overflow-x-auto">
                <span className="text-accent-blue select-none">$</span>
                <span>{getCommand()}</span>
              </div>
              <button
                onClick={() => copyText(getCommand(), "install-hero")}
                className="text-text-muted hover:text-text-primary transition-colors p-1"
                aria-label="Copy install command"
              >
                {copiedCmd === "install-hero" ? (
                  <Check className="w-4 h-4 text-accent-emerald" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </motion.div>

          {/* Value Feature Highlights */}
          <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-3xl mx-auto pt-6 border-t border-border-subtle">
            <div className="flex flex-col items-center">
              <span className="text-xl sm:text-2xl font-bold font-mono text-text-primary">9.2ms</span>
              <span className="text-xs text-text-muted mt-0.5">MCP Search Latency</span>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-xl sm:text-2xl font-bold font-mono text-accent-emerald">99.3%</span>
              <span className="text-xs text-text-muted mt-0.5">Token Reduction</span>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-xl sm:text-2xl font-bold font-mono text-text-primary">3 Layers</span>
              <span className="text-xs text-text-muted mt-0.5">Graph + Wiki + Memory</span>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-xl sm:text-2xl font-bold font-mono text-accent-blue">100% Local</span>
              <span className="text-xs text-text-muted mt-0.5">SQLite & Tree-sitter</span>
            </div>
          </div>
        </div>

        {/* Live Interactive Dual-Engine Sandbox */}
        <div className="mt-14 max-w-5xl mx-auto">
          <div className="minimal-card overflow-hidden shadow-2xl">
            {/* Sandbox Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-subtle">
              <div className="flex items-center gap-2">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#ef4444]/60"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]/60"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-[#10b981]/60"></div>
                </div>
                <span className="text-xs font-mono text-text-muted ml-2">synap://runtime-inspector</span>
              </div>

              {/* View Switcher Tabs */}
              <div className="flex items-center bg-surface border border-border rounded-lg p-0.5 text-xs font-mono">
                <button
                  onClick={() => setActiveView("graph")}
                  className={`px-3 py-1 rounded-md transition-all ${activeView === "graph" ? "bg-surface-hover text-text-primary font-medium border border-border" : "text-text-muted hover:text-text-primary"}`}
                >
                  AST Graph (L1)
                </button>
                <button
                  onClick={() => setActiveView("mcp")}
                  className={`px-3 py-1 rounded-md transition-all ${activeView === "mcp" ? "bg-surface-hover text-text-primary font-medium border border-border" : "text-text-muted hover:text-text-primary"}`}
                >
                  FastMCP Protocol
                </button>
                <button
                  onClick={() => setActiveView("savings")}
                  className={`px-3 py-1 rounded-md transition-all ${activeView === "savings" ? "bg-surface-hover text-text-primary font-medium border border-border" : "text-text-muted hover:text-text-primary"}`}
                >
                  Token Economics
                </button>
              </div>
            </div>

            {/* Sandbox Content Area */}
            <div className="p-6 bg-[#0B0D14]">
              {activeView === "graph" && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Left: Node Selector */}
                  <div className="space-y-2 font-mono text-xs">
                    <div className="text-[11px] font-semibold text-text-muted tracking-wider uppercase mb-3">
                      Discovered AST Symbol Entities
                    </div>
                    {GRAPH_NODES.map(node => (
                      <button
                        key={node.id}
                        onClick={() => setSelectedNode(node)}
                        className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between ${selectedNode.id === node.id ? "bg-surface-hover border-accent-blue/50 text-text-primary" : "bg-surface/50 border-border text-text-secondary hover:border-border-strong"}`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${node.layer === "L1" ? "bg-accent-blue/15 text-accent-blue" : node.layer === "L2" ? "bg-accent-emerald/15 text-accent-emerald" : "bg-accent-amber/15 text-accent-amber"}`}>
                            {node.layer}
                          </span>
                          <span className="font-medium">{node.name}</span>
                        </div>
                        <span className="text-[11px] text-text-muted">{node.tokens} tok</span>
                      </button>
                    ))}
                  </div>

                  {/* Center & Right: Node Inspector Details */}
                  <div className="md:col-span-2 bg-surface rounded-xl border border-border p-5 font-mono text-xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between pb-3 border-b border-border">
                        <div className="flex items-center gap-2">
                          <Code2 className="w-4 h-4 text-accent-blue" />
                          <span className="font-bold text-text-primary text-sm">{selectedNode.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-subtle border border-border text-text-muted">
                            {selectedNode.type}
                          </span>
                        </div>
                        <span className="text-text-muted">{selectedNode.file}</span>
                      </div>

                      <div className="mt-4 space-y-3">
                        <div>
                          <span className="text-text-muted block text-[11px]">Purpose / Description:</span>
                          <p className="text-text-secondary mt-1 font-sans">{selectedNode.detail}</p>
                        </div>

                        <div>
                          <span className="text-text-muted block text-[11px]">Symbol Graph References:</span>
                          <div className="flex flex-wrap gap-2 mt-1.5">
                            {selectedNode.connections.length > 0 ? (
                              selectedNode.connections.map(connId => {
                                const target = GRAPH_NODES.find(n => n.id === connId)
                                return (
                                  <span key={connId} className="px-2 py-1 rounded bg-surface-subtle border border-border text-accent-blue flex items-center gap-1">
                                    → {target?.name}
                                  </span>
                                )
                              })
                            ) : (
                              <span className="text-text-muted">Terminal edge (Leaf entity)</span>
                            )}
                          </div>
                        </div>

                        <div className="pt-3 border-t border-border/60">
                          <span className="text-text-muted block text-[11px]">SQLite Graph Query Representation:</span>
                          <pre className="mt-2 p-2.5 rounded bg-[#090A0F] border border-border text-[11px] text-text-secondary overflow-x-auto">
{`SELECT s.symbol_id, s.name, s.kind, e.target_symbol_id
FROM symbols s
JOIN edges e ON s.symbol_id = e.source_symbol_id
WHERE s.file_id = hash('${selectedNode.file}')
AND s.git_oid = '${activeBranch === "main" ? "a14f9bc" : "d820ef1"}';`}
                          </pre>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-text-muted text-[11px]">
                      <span>Indexed via Tree-sitter in 0.4ms</span>
                      <span className="text-accent-emerald flex items-center gap-1">
                        <Check className="w-3 h-3" /> Grounded Context Ready
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {activeView === "mcp" && (
                <div className="space-y-4 font-mono text-xs">
                  <div className="flex items-center justify-between text-text-muted pb-2 border-b border-border">
                    <span className="text-accent-emerald flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5" /> MCP Tool Invocation: search(query="resolve_imports")
                    </span>
                    <span className="text-text-muted">Latency: 9.2ms (Deterministic Intent Routing)</span>
                  </div>

                  <pre className="p-4 rounded-xl bg-[#090A0F] border border-border text-text-secondary overflow-x-auto text-[11px] leading-relaxed">
{`{
  "jsonrpc": "2.0",
  "result": {
    "grounded_context": {
      "symbols": [
        { "name": "resolve_imports", "kind": "function", "file": "src/synap_git/parser/registry.py", "lines": "125-145" },
        { "name": "TreeSitterRegistry", "kind": "class", "file": "src/synap_git/parser/registry.py", "lines": "30-180" }
      ],
      "dependencies": [
        "src/synap_git/storage/sqlite.py",
        "src/synap_git/indexer/engine.py"
      ],
      "wiki_summary": "Registry dynamically resolves multi-language Tree-sitter grammars (py, ts, rs, go, c, cpp) into unified edge tables."
    },
    "tokens_provided": 420,
    "tokens_raw_files_avoided": 48500,
    "synthesized_answer": false
  }
}`}
                  </pre>
                </div>
              )}

              {activeView === "savings" && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 font-mono text-xs">
                  <div className="p-4 rounded-xl bg-surface border border-border flex flex-col justify-between">
                    <span className="text-text-muted uppercase text-[10px] tracking-wider">Raw File Dump Method</span>
                    <div className="my-3">
                      <span className="text-2xl font-bold text-[#ef4444]">182,000</span>
                      <span className="text-xs text-text-muted block mt-1">tokens / query</span>
                    </div>
                    <span className="text-[11px] text-text-muted">Bloats context, risks hallucinations, slow response times</span>
                  </div>

                  <div className="p-4 rounded-xl bg-surface border border-border flex flex-col justify-between">
                    <span className="text-text-muted uppercase text-[10px] tracking-wider">Vector-Only RAG</span>
                    <div className="my-3">
                      <span className="text-2xl font-bold text-accent-amber">12,400</span>
                      <span className="text-xs text-text-muted block mt-1">tokens / query</span>
                    </div>
                    <span className="text-[11px] text-text-muted">Misses call-hierarchies and AST class relationships</span>
                  </div>

                  <div className="p-4 rounded-xl bg-surface border border-accent-emerald/40 bg-accent-emerald/5 flex flex-col justify-between">
                    <span className="text-accent-emerald uppercase text-[10px] tracking-wider font-bold">Synapse 3-Layer Engine</span>
                    <div className="my-3">
                      <span className="text-2xl font-bold text-accent-emerald">1,240</span>
                      <span className="text-xs text-accent-emerald/80 block mt-1">tokens / query (99.3% savings)</span>
                    </div>
                    <span className="text-[11px] text-text-secondary">Exact AST caller/callee context, instant 9.2ms retrieval</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </section>
  )
}
