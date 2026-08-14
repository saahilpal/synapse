"use client"

import React, { useState } from "react"
import { Layers, Check, Copy, Terminal, ShieldCheck, Zap } from "lucide-react"

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
    name: "search",
    description: "Performs hybrid AST, lexical, and semantic retrieval returning grounded context in 9.2ms.",
    requestPayload: {
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: {
        name: "search",
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
        query_time_ms: 9.2,
        tokens_provided: 420,
        symbols_found: 2,
        context: [
          { symbol: "class TreeSitterRegistry", file: "src/synap_git/parser/registry.py", lines: "30-180" },
          { symbol: "def parse_ast()", file: "src/synap_git/parser/registry.py", lines: "125-145" }
        ],
        synthesize_answer: false
      }
    }
  },
  {
    id: "log_decision",
    name: "log_decision",
    description: "Records an architectural or technical decision into L3 memory for future agent context.",
    requestPayload: {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: {
        name: "log_decision",
        arguments: {
          decision: "Use SQLite WAL mode and PRAGMA synchronous = NORMAL",
          rationale: "Ensures concurrent async readers without blocking write transactions during Git re-indexing.",
          tags: ["architecture", "storage", "sqlite"]
        }
      }
    },
    responsePayload: {
      jsonrpc: "2.0",
      id: 2,
      result: {
        status: "logged",
        decision_id: "dec_7f10a8",
        active_constraints_count: 5
      }
    }
  },
  {
    id: "checkpoint",
    name: "create_checkpoint",
    description: "Saves an L3 task checkpoint (doing, changed_files, next_step, blockers) across sessions.",
    requestPayload: {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: {
        name: "create_checkpoint",
        arguments: {
          doing: "Refactoring LRU vector dot-product cache in sqlite.py",
          changed_files: ["src/synap_git/storage/sqlite.py"],
          next_step: "Run pytest tests/test_retrieval_and_budgeting.py",
          blockers: "None"
        }
      }
    },
    responsePayload: {
      jsonrpc: "2.0",
      id: 3,
      result: {
        status: "saved",
        checkpoint_id: "chk_9a41b2",
        timestamp: "2026-08-14T19:20:00Z"
      }
    }
  },
  {
    id: "get_memory",
    name: "get_memory",
    description: "Fetches active architectural constraints, approved revert lessons, and checkpoints.",
    requestPayload: {
      jsonrpc: "2.0",
      id: 4,
      method: "tools/call",
      params: {
        name: "get_memory",
        arguments: {
          limit: 10
        }
      }
    },
    responsePayload: {
      jsonrpc: "2.0",
      id: 4,
      result: {
        approved_lessons: 4,
        checkpoints: 2,
        active_decisions: 8
      }
    }
  }
]

export function McpInspector() {
  const [selectedTool, setSelectedTool] = useState<McpTool>(MCP_TOOLS[0])
  const [activeTab, setActiveTab] = useState<"request" | "response">("response")
  const [copied, setCopied] = useState(false)

  const copyPayload = () => {
    const payload = activeTab === "request" ? selectedTool.requestPayload : selectedTool.responsePayload
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section id="mcp" className="py-20 bg-[#090A0F] border-b border-border-subtle">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="max-w-3xl mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-text-secondary text-xs font-mono mb-4">
            <Zap className="w-3.5 h-3.5 text-accent-emerald" />
            <span>Model Context Protocol</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary tracking-tight">
            FastMCP Protocol Inspector.
          </h2>
          <p className="mt-3 text-text-secondary font-sans text-sm sm:text-base leading-relaxed">
            Inspect the raw JSON-RPC standard I/O messages exchanged between coding agents and Synapse. All responses are token-budgeted and optimized for instant context injection.
          </p>
        </div>

        {/* MCP Tool Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

          {/* Tool Selector List */}
          <div className="lg:col-span-4 space-y-2 font-mono text-xs">
            {MCP_TOOLS.map(tool => (
              <button
                key={tool.id}
                onClick={() => setSelectedTool(tool)}
                className={`w-full text-left p-3.5 rounded-xl border transition-all flex items-center justify-between cursor-pointer ${
                  selectedTool.id === tool.id
                    ? "bg-surface-hover border-accent-blue/50 text-text-primary font-medium shadow-md"
                    : "bg-surface/50 border-border text-text-secondary hover:border-border-strong hover:bg-surface"
                }`}
              >
                <div>
                  <span className="font-semibold">{tool.name}</span>
                  <p className="text-[11px] text-text-muted mt-0.5 line-clamp-1 font-sans">
                    {tool.description}
                  </p>
                </div>
              </button>
            ))}
          </div>

          {/* JSON-RPC Inspector Window */}
          <div className="lg:col-span-8 minimal-card overflow-hidden font-mono text-xs shadow-2xl">
            {/* Header with Request/Response tabs */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-subtle">
              <div className="flex items-center gap-2">
                <div className="flex bg-surface border border-border rounded-lg p-0.5">
                  <button
                    onClick={() => setActiveTab("response")}
                    className={`px-3 py-1 rounded-md transition-all ${
                      activeTab === "response"
                        ? "bg-surface-hover text-accent-emerald font-semibold border border-border"
                        : "text-text-muted hover:text-text-primary"
                    }`}
                  >
                    Tool Result (Response)
                  </button>
                  <button
                    onClick={() => setActiveTab("request")}
                    className={`px-3 py-1 rounded-md transition-all ${
                      activeTab === "request"
                        ? "bg-surface-hover text-accent-blue font-semibold border border-border"
                        : "text-text-muted hover:text-text-primary"
                    }`}
                  >
                    Agent Call (Request)
                  </button>
                </div>
              </div>

              <button
                onClick={copyPayload}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface border border-border text-text-muted hover:text-text-primary transition-all cursor-pointer text-[11px]"
              >
                {copied ? <Check className="w-3 h-3 text-accent-emerald" /> : <Copy className="w-3 h-3" />}
                <span>{copied ? "Copied" : "Copy JSON"}</span>
              </button>
            </div>

            {/* JSON Content */}
            <div className="p-5 bg-[#08090D] min-h-[280px] overflow-x-auto text-[11px] leading-relaxed">
              <pre className={activeTab === "response" ? "text-accent-emerald" : "text-accent-blue"}>
                {JSON.stringify(activeTab === "request" ? selectedTool.requestPayload : selectedTool.responsePayload, null, 2)}
              </pre>
            </div>
          </div>

        </div>

      </div>
    </section>
  )
}
