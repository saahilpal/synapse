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
  Sparkles,
  GitCommit,
  RefreshCw,
  Code2
} from "lucide-react"

interface GraphNode {
  id: string
  name: string
  type: "class" | "function" | "import" | "wiki"
  layer: "L1" | "L2" | "L3"
  connections: string[]
  tokens: number
  file: string
  status: "active" | "idle"
}

const INITIAL_NODES: GraphNode[] = [
  { id: "node-1", name: "SynapRuntime", type: "class", layer: "L1", connections: ["node-2", "node-3"], tokens: 180, file: "indexer/engine.py", status: "active" },
  { id: "node-2", name: "query_hybrid()", type: "function", layer: "L1", connections: ["node-4", "node-5"], tokens: 145, file: "retrieval/engine.py", status: "active" },
  { id: "node-3", name: "TreeSitterRegistry", type: "class", layer: "L1", connections: ["node-6"], tokens: 210, file: "parser/registry.py", status: "idle" },
  { id: "node-4", name: "SQLiteStorage (WAL)", type: "class", layer: "L1", connections: [], tokens: 320, file: "storage/sqlite.py", status: "active" },
  { id: "node-5", name: "WikiWorkerTask", type: "function", layer: "L2", connections: ["node-7"], tokens: 190, file: "indexer/wiki.py", status: "idle" },
  { id: "node-6", name: "RevertLessonDetector", type: "class", layer: "L3", connections: [], tokens: 160, file: "git/state.py", status: "idle" },
  { id: "node-7", name: "FastMCPFacade", type: "class", layer: "L1", connections: ["node-2"], tokens: 175, file: "mcp/server.py", status: "active" }
]

export function SynapseHero() {
  const [copied, setCopied] = useState(false)
  const [activeBranch, setActiveBranch] = useState("main")
  const [isCommitShifting, setIsCommitShifting] = useState(false)
  const [selectedNode, setSelectedNode] = useState<GraphNode>(INITIAL_NODES[0])
  const [activeTab, setActiveTab] = useState<"graph" | "diff" | "mcp">("graph")

  const copyInstallCommand = () => {
    navigator.clipboard.writeText("pip install synap-git")
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const triggerBranchSwap = () => {
    setIsCommitShifting(true)
    setTimeout(() => {
      setActiveBranch(prev => prev === "main" ? "feature/ast-cte-v2" : "main")
      setIsCommitShifting(false)
    }, 500)
  }

  return (
    <section className="relative pt-12 pb-20 md:pt-20 md:pb-28 border-b border-slate-800/80 bg-grid-pattern">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">

        {/* Top Git Projection Indicator */}
        <div className="flex justify-center mb-8">
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-slate-900 border border-slate-700/80 text-xs font-mono text-slate-300 shadow-sm hover:border-slate-600 transition-all cursor-pointer"
            onClick={triggerBranchSwap}
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-slate-400">Git OID Projection:</span>
            <span className="text-emerald-400 font-semibold flex items-center gap-1">
              <GitCommit className="w-3 h-3" /> {activeBranch}
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-sky-400 flex items-center gap-1 hover:underline">
              <RefreshCw className={`w-3 h-3 ${isCommitShifting ? "animate-spin text-sky-300" : ""}`} />
              Simulate Commit Shift (4.8ms)
            </span>
          </motion.div>
        </div>

        {/* Hero Title & Value Proposition */}
        <div className="text-center max-w-4xl mx-auto">
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="text-4xl sm:text-6xl lg:text-7xl font-display font-bold tracking-tight text-slate-100 leading-[1.1]"
          >
            Deterministic Git-Aware <br className="hidden sm:inline" />
            <span className="text-sky-400">Structural Context Engine</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="mt-6 text-base sm:text-lg text-slate-400 max-w-3xl mx-auto leading-relaxed font-sans"
          >
            Stop burning 100k tokens dumping raw source files into AI context windows.
            <strong className="text-slate-200 font-semibold"> Synapse</strong> projects Git repository commits into an SQLite AST code graph and serves token-budgeted context via stdio MCP.
          </motion.p>

          {/* Action Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="mt-8 flex flex-wrap items-center justify-center gap-4"
          >
            <div className="flex items-center bg-slate-900 border border-slate-700/90 rounded-xl p-1.5 shadow-md font-mono text-sm">
              <div className="flex items-center gap-2 px-3 py-1 text-slate-300">
                <Terminal className="w-4 h-4 text-sky-400" />
                <span className="text-slate-500">$</span>
                <span className="text-slate-100 font-semibold">pip install synap-git</span>
              </div>
              <button
                onClick={copyInstallCommand}
                className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-600 rounded-lg px-3 py-1.5 transition-all text-xs font-sans font-medium"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            </div>

            <a
              href="#architecture"
              className="inline-flex items-center gap-2 bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl px-5 py-3 font-medium text-sm transition-all"
            >
              <span>Explore HLD Architecture</span>
              <ArrowRight className="w-4 h-4 text-slate-400" />
            </a>
          </motion.div>

          {/* Feature Badges */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-6 text-xs font-mono text-slate-400">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>100% Local SQLite WAL Engine</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-sky-400" />
              <span>4.8ms Graph CTE Traversal</span>
            </div>
            <div className="flex items-center gap-1.5">
              <GitBranch className="w-4 h-4 text-slate-300" />
              <span>Zero-Disk Rescan on Commit Shift</span>
            </div>
          </div>
        </div>

        {/* Interactive Neural AST Graph Demo */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="mt-12 lg:mt-14 tech-card overflow-hidden shadow-xl"
        >
          {/* Header */}
          <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-slate-700" />
                <div className="w-3 h-3 rounded-full bg-slate-700" />
                <div className="w-3 h-3 rounded-full bg-slate-700" />
              </div>
              <span className="text-xs font-mono text-slate-400 border-l border-slate-800 pl-3 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-sky-400" />
                synap-daemon // commit: {isCommitShifting ? "shifting..." : "a4f8e91"}
              </span>
            </div>

            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-xs font-mono">
              <button
                onClick={() => setActiveTab("graph")}
                className={`px-3 py-1 rounded-md flex items-center gap-1.5 transition-all ${
                  activeTab === "graph" ? "bg-slate-800 text-sky-400 font-medium" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Code2 className="w-3.5 h-3.5" />
                L1 AST Graph
              </button>
              <button
                onClick={() => setActiveTab("diff")}
                className={`px-3 py-1 rounded-md flex items-center gap-1.5 transition-all ${
                  activeTab === "diff" ? "bg-slate-800 text-emerald-400 font-medium" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <GitCommit className="w-3.5 h-3.5" />
                Git Delta Engine
              </button>
              <button
                onClick={() => setActiveTab("mcp")}
                className={`px-3 py-1 rounded-md flex items-center gap-1.5 transition-all ${
                  activeTab === "mcp" ? "bg-slate-800 text-amber-400 font-medium" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                MCP Stdio Packet
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="p-6 bg-slate-950 min-h-[380px] grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">

            {activeTab === "graph" && (
              <>
                {/* Left: AST Nodes */}
                <div className="lg:col-span-7 bg-slate-900/60 border border-slate-800 rounded-xl p-5 relative overflow-hidden min-h-[320px] flex flex-col justify-between">
                  <div className="absolute inset-0 bg-dots-pattern opacity-40 pointer-events-none" />

                  <div className="relative z-10 flex items-center justify-between text-xs font-mono mb-4 pb-2 border-b border-slate-800">
                    <span className="text-slate-400 flex items-center gap-1.5">
                      <Search className="w-3.5 h-3.5 text-sky-400" />
                      Query Target: &quot;SynapRuntime&quot;
                    </span>
                    <span className="text-emerald-400 flex items-center gap-1">
                      <Database className="w-3.5 h-3.5" /> SQLite CTE Traversal
                    </span>
                  </div>

                  <div className="relative z-10 grid grid-cols-2 sm:grid-cols-3 gap-3 my-auto">
                    {INITIAL_NODES.map((node) => {
                      const isSelected = selectedNode.id === node.id
                      return (
                        <div
                          key={node.id}
                          onClick={() => setSelectedNode(node)}
                          className={`cursor-pointer p-3 rounded-xl border text-left transition-all ${
                            isSelected
                              ? "bg-slate-800/90 border-sky-500 text-slate-100 ring-1 ring-sky-500/30"
                              : "bg-slate-900/90 border-slate-800 text-slate-300 hover:border-slate-700"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                              node.layer === "L1" ? "bg-sky-950 text-sky-300 border border-sky-800" : node.layer === "L2" ? "bg-emerald-950 text-emerald-300 border border-emerald-800" : "bg-amber-950 text-amber-300 border border-amber-800"
                            }`}>
                              {node.layer}
                            </span>
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          </div>
                          <h4 className="text-xs font-mono font-semibold text-slate-100 truncate">{node.name}</h4>
                          <p className="text-[11px] font-mono text-slate-400 truncate mt-0.5">{node.file}</p>
                          <div className="mt-2 pt-1.5 border-t border-slate-800 flex items-center justify-between text-[10px] font-mono text-slate-400">
                            <span>{node.type}</span>
                            <span className="text-sky-400">{node.tokens} tok</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div className="relative z-10 mt-4 text-[11px] font-mono text-slate-400 flex items-center justify-between">
                    <span>Click symbol node to inspect primary keys</span>
                    <span className="text-sky-400">7 AST symbols active</span>
                  </div>
                </div>

                {/* Right: Symbol Inspector */}
                <div className="lg:col-span-5 flex flex-col justify-between bg-slate-900 border border-slate-800 rounded-xl p-5 font-mono text-xs min-h-[320px]">
                  <div>
                    <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-slate-300">
                      <span className="font-semibold text-sky-400 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-sky-400" />
                        Symbol Inspector: {selectedNode.name}
                      </span>
                      <span className="px-2 py-0.5 bg-slate-800 text-slate-300 text-[10px] rounded border border-slate-700">
                        {selectedNode.layer} Layer
                      </span>
                    </div>

                    <div className="mt-4 space-y-2 text-slate-400 text-[11px]">
                      <div className="flex justify-between border-b border-slate-800/60 pb-1">
                        <span className="text-slate-500">File Path:</span>
                        <span className="text-slate-200">{selectedNode.file}</span>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/60 pb-1">
                        <span className="text-slate-500">AST Symbol Type:</span>
                        <span className="text-sky-400">{selectedNode.type}</span>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/60 pb-1">
                        <span className="text-slate-500">SHA256 Content Key:</span>
                        <span className="text-emerald-400">sha256(path + content_hash)</span>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/60 pb-1">
                        <span className="text-slate-500">Token Weight:</span>
                        <span className="text-amber-400">{selectedNode.tokens} tokens</span>
                      </div>
                    </div>

                    <div className="mt-4 bg-slate-950 p-3 rounded-lg border border-slate-800 text-[11px] leading-relaxed text-slate-300">
                      <div className="text-slate-500 text-[10px] mb-1">{`// SQLite Recursive CTE Expansion`}</div>
                      <pre className="overflow-x-auto text-sky-300">
{`WITH RECURSIVE graph_cte AS (
  SELECT id, name, file_path, 0 AS depth
  FROM symbols WHERE name = '${selectedNode.name}'
  UNION ALL
  SELECT s.id, s.name, s.file_path, g.depth + 1
  FROM symbols s JOIN edges e ON s.id = e.target_id
  JOIN graph_cte g ON e.source_id = g.id
  WHERE g.depth < 2
) SELECT * FROM graph_cte;`}
                      </pre>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between text-[10px] text-slate-400">
                    <span className="flex items-center gap-1 text-emerald-400">
                      <ShieldCheck className="w-3.5 h-3.5" /> Grounded Context Engine
                    </span>
                    <span className="text-slate-400">tiktoken budget: 4,000</span>
                  </div>
                </div>
              </>
            )}

            {activeTab === "diff" && (
              <div className="lg:col-span-12 bg-slate-900 border border-slate-800 rounded-xl p-6 font-mono text-xs text-slate-300 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <span className="text-emerald-400 font-semibold flex items-center gap-2">
                    <GitCommit className="w-4 h-4" /> Git Delta Classification — Commit {activeBranch === "main" ? "a4f8e91" : "c72b109"}
                  </span>
                  <span className="text-xs bg-slate-800 text-slate-400 px-2.5 py-1 rounded-md border border-slate-700">
                    watchdog event-driven
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                    <div className="text-[11px] text-slate-500 font-bold uppercase tracking-wider">Modified & Renamed Files (git diff-tree -M)</div>
                    <div className="text-emerald-400 flex items-center gap-2">
                      <span className="px-1.5 py-0.5 bg-emerald-950 border border-emerald-800 text-[10px] rounded">R100</span>
                      <span>src/synap_git/parser/old_registry.py → registry.py</span>
                    </div>
                    <div className="text-sky-400 flex items-center gap-2">
                      <span className="px-1.5 py-0.5 bg-sky-950 border border-sky-800 text-[10px] rounded">M</span>
                      <span>src/synap_git/indexer/daemon.py</span>
                    </div>
                    <div className="text-amber-400 flex items-center gap-2">
                      <span className="px-1.5 py-0.5 bg-amber-950 border border-amber-800 text-[10px] rounded">A</span>
                      <span>tests/test_audit_fixes_aug2026.py</span>
                    </div>
                  </div>

                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                    <div className="text-[11px] text-slate-500 font-bold uppercase tracking-wider">Symbol Edge Migration</div>
                    <p className="text-slate-400 text-[11px]">
                      File renames preserve primary keys and edge records in SQLite without executing cascading deletions.
                    </p>
                    <div className="mt-3 p-2 bg-slate-900 rounded border border-slate-800 text-[10px] text-slate-300">
                      UPDATE files SET file_id = &apos;new_sha&apos;, path = &apos;new_path&apos; WHERE file_id = &apos;old_sha&apos;
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "mcp" && (
              <div className="lg:col-span-12 bg-slate-900 border border-slate-800 rounded-xl p-6 font-mono text-xs text-slate-300 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <span className="text-amber-400 font-semibold flex items-center gap-2">
                    <Layers className="w-4 h-4" /> FastMCP Stdio Packet Protocol
                  </span>
                  <span className="text-xs bg-slate-800 text-slate-400 px-2.5 py-1 rounded-md border border-slate-700">
                    stdio transport
                  </span>
                </div>

                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 overflow-x-auto text-[11px] text-amber-300 space-y-2">
                  <div className="text-slate-500">{`// FastMCP JSON-RPC 2.0 stdio stream`}</div>
                  <pre>{`{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "synap_search",
    "arguments": { "query": "TreeSitterRegistry", "max_tokens": 4000 }
  }
}`}</pre>
                </div>
              </div>
            )}

          </div>
        </motion.div>

      </div>
    </section>
  )
}
