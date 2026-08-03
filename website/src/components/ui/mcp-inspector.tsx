"use client"

import React, { useState } from "react"
import {
  Layers,
  Check,
  Copy,
  Terminal,
  ShieldCheck
} from "lucide-react"

interface McpTool {
  id: string
  name: string
  description: string
  requestPayload: object
  responsePayload: object
}

const MCP_TOOLS: McpTool[] = [
  {
    id: "search",
    name: "synap_search",
    description: "Executes hybrid graph CTE & FTS5 search with tiktoken context budgeting.",
    requestPayload: {
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: {
        name: "synap_search",
        arguments: {
          query: "TreeSitterRegistry",
          max_tokens: 4000
        }
      }
    },
    responsePayload: {
      jsonrpc: "2.0",
      id: 1,
      result: {
        status: "success",
        query_time_ms: 4.8,
        token_count: 540,
        symbols_found: 3,
        context: [
          { symbol: "class TreeSitterRegistry", file: "src/synap_git/parser/registry.py", lines: "45-120" },
          { symbol: "def parse_ast()", file: "src/synap_git/parser/registry.py", lines: "85-110" }
        ]
      }
    }
  },
  {
    id: "checkpoint",
    name: "synap_create_checkpoint",
    description: "Saves an L3 task state snapshot (doing, changed_files, next_step, blockers).",
    requestPayload: {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: {
        name: "synap_create_checkpoint",
        arguments: {
          doing: "Refactoring SQLite WAL transaction pool",
          changed_files: ["src/synap_git/storage/sqlite.py"],
          next_step: "Run pytest -v tests/test_storage.py",
          blockers: "None"
        }
      }
    },
    responsePayload: {
      jsonrpc: "2.0",
      id: 2,
      result: {
        status: "success",
        checkpoint_id: "cp_99182a4d",
        branch: "main",
        git_commit: "a4f8e91"
      }
    }
  },
  {
    id: "decision",
    name: "synap_log_decision",
    description: "Logs an architectural decision into L3 behavioral memory.",
    requestPayload: {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: {
        name: "synap_log_decision",
        arguments: {
          content: "Use PRAGMA synchronous = NORMAL with WAL mode for I/O safety",
          context_info: "Avoids disk flush bottlenecks during bulk AST parsing"
        }
      }
    },
    responsePayload: {
      jsonrpc: "2.0",
      id: 3,
      result: {
        status: "success",
        decision_id: "dec_7710b2f"
      }
    }
  },
  {
    id: "memory",
    name: "synap_get_approved_memory",
    description: "Fetches active approved revert lessons to inject into system prompt.",
    requestPayload: {
      jsonrpc: "2.0",
      id: 4,
      method: "tools/call",
      params: {
        name: "synap_get_approved_memory",
        arguments: {}
      }
    },
    responsePayload: {
      jsonrpc: "2.0",
      id: 4,
      result: {
        status: "success",
        lessons: [
          {
            lesson_id: "les_9921a8f",
            rule: "Never execute blocking SQLite calls on main loop; wrap in asyncio.to_thread()",
            actor: "mcp_agent"
          }
        ]
      }
    }
  }
]

export function McpInspector() {
  const [selectedToolId, setSelectedToolId] = useState<string>("search")
  const [copied, setCopied] = useState(false)
  const selectedTool = MCP_TOOLS.find(t => t.id === selectedToolId) || MCP_TOOLS[0]

  const handleCopyPayload = () => {
    navigator.clipboard.writeText(JSON.stringify(selectedTool.requestPayload, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section id="mcp" className="py-20 bg-slate-950 border-b border-slate-800/80 relative">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300 mb-3">
            <Layers className="w-3.5 h-3.5 text-emerald-400" />
            <span>Model Context Protocol (MCP)</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-bold text-slate-100 tracking-tight">
            Native Stdio Integration for AI Agents
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg font-sans">
            Connects seamlessly to <strong className="text-slate-200">Cursor, Windsurf, Claude Desktop, Antigravity, and Continue</strong> via standard FastMCP JSON-RPC stdio.
          </p>
        </div>

        {/* MCP Wire Inspector Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">

          {/* Tool Selector List */}
          <div className="lg:col-span-4 space-y-3">
            <div className="text-xs font-mono text-slate-400 mb-2 uppercase tracking-wider px-1">
              Exposed FastMCP Stdio Tools
            </div>

            {MCP_TOOLS.map(tool => {
              const isSelected = tool.id === selectedToolId
              return (
                <button
                  key={tool.id}
                  onClick={() => setSelectedToolId(tool.id)}
                  className={`w-full p-4 rounded-xl border text-left transition-all font-mono ${
                    isSelected
                      ? "bg-slate-900 border-emerald-500 text-slate-100 ring-1 ring-emerald-500/30"
                      : "bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-emerald-400">{tool.name}</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  </div>
                  <p className="text-[11px] font-sans text-slate-400 line-clamp-2 mt-1">
                    {tool.description}
                  </p>
                </button>
              )
            })}

            {/* FastMCP Config Snippet */}
            <div className="mt-6 p-4 rounded-xl bg-slate-900 border border-slate-800 font-mono text-xs text-slate-300">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                <span>mcp_config.json snippet</span>
                <span className="text-emerald-400">stdio</span>
              </div>
              <pre className="text-[10px] text-slate-400 bg-slate-950 p-2.5 rounded-lg border border-slate-800 overflow-x-auto">
{`"synapse": {
  "command": "synap",
  "args": ["mcp", "."]
}`}
              </pre>
            </div>
          </div>

          {/* JSON-RPC Inspector */}
          <div className="lg:col-span-8 tech-card p-6 border border-slate-800 font-mono text-xs flex flex-col justify-between min-h-[460px] bg-slate-950">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <span className="text-slate-300 font-semibold flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-emerald-400" />
                  JSON-RPC Wire Packet: <span className="text-emerald-400">{selectedTool.name}</span>
                </span>
                <button
                  onClick={handleCopyPayload}
                  className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[11px] transition-all border border-slate-700"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? "Copied" : "Copy Payload"}</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">

                {/* Outgoing Request */}
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                    <span className="text-sky-400">▶ Stdio Request (Agent → Synapse)</span>
                  </div>
                  <pre className="text-[11px] text-sky-300 overflow-x-auto leading-relaxed">
{JSON.stringify(selectedTool.requestPayload, null, 2)}
                  </pre>
                </div>

                {/* Incoming Response */}
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                    <span className="text-emerald-400">◀ Stdio Response (Synapse → Agent)</span>
                  </div>
                  <pre className="text-[11px] text-emerald-300 overflow-x-auto leading-relaxed">
{JSON.stringify(selectedTool.responsePayload, null, 2)}
                  </pre>
                </div>

              </div>
            </div>

            <div className="mt-6 pt-3 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
              <span className="flex items-center gap-1.5 text-emerald-400">
                <ShieldCheck className="w-3.5 h-3.5" /> Schema Validated via FastMCP
              </span>
              <span className="text-slate-400">Latency: 4.8ms</span>
            </div>

          </div>

        </div>

      </div>
    </section>
  )
}
