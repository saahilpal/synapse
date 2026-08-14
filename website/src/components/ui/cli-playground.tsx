"use client"

import React, { useState } from "react"
import { Terminal as TerminalIcon, Check, Copy, Play } from "lucide-react"

interface CommandSpec {
  id: string
  cmd: string
  label: string
  description: string
  logs: { text: string; type: "cmd" | "info" | "success" | "warning" | "title" }[]
}

const CLI_SPECS: CommandSpec[] = [
  {
    id: "init",
    cmd: "synap init .",
    label: "synap init",
    description: "Initializes SQLite schema, extracts AST symbol definitions, and seeds documentation.",
    logs: [
      { text: "❯ synap init .", type: "cmd" },
      { text: "Synapse: Initializing Repository Context Engine", type: "title" },
      { text: "✔ Git root verified: /workspace/synapse (branch: main)", type: "success" },
      { text: "✔ Tree-sitter parsers initialized (25+ grammar definitions)", type: "info" },
      { text: "✔ Database schema created: .synap/synap.db (WAL Mode)", type: "success" },
      { text: "› Pass 1: Parsing AST symbol graphs across 1,120 files... (380ms)", type: "info" },
      { text: "› Pass 2: Resolving caller/callee dependency edges... (120ms)", type: "info" },
      { text: "✔ Indexed 8,421 symbols and 14,290 dependency edges.", type: "success" },
      { text: "✔ Structural context engine initialized successfully.", type: "success" }
    ]
  },
  {
    id: "index",
    cmd: "synap index .",
    label: "synap index",
    description: "Explicitly re-indexes all AST symbols, dependencies, and vector embeddings into SQLite.",
    logs: [
      { text: "❯ synap index .", type: "cmd" },
      { text: "› Scanning modified files against Git HEAD...", type: "info" },
      { text: "› AST parsing [████████████████████] 100% (1,120/1,120 files)", type: "info" },
      { text: "› Generating vector embeddings with nomic-embed-text (Ollama localhost)...", type: "info" },
      { text: "✔ Vector indexing completed in 1.4s (0 tokens spent / 100% local)", type: "success" },
      { text: "✔ SQLite database updated: 8,421 symbols, 1,120 files fresh.", type: "success" }
    ]
  },
  {
    id: "sync",
    cmd: "synap sync .",
    label: "synap sync",
    description: "Incrementally synchronizes the SQLite index with recent Git commits in under 5ms.",
    logs: [
      { text: "❯ synap sync .", type: "cmd" },
      { text: "› Git OID detected: d91a4b (3 commits ahead)", type: "info" },
      { text: "› Analyzing diff delta (2 modified files, 0 deleted)...", type: "info" },
      { text: "  • Updated: src/synap_git/retrieval/engine.py (+14 symbols)", type: "success" },
      { text: "  • Updated: src/synap_git/storage/sqlite.py (+3 symbols)", type: "success" },
      { text: "✔ Incremental sync completed in 4.8ms.", type: "success" }
    ]
  },
  {
    id: "search",
    cmd: 'synap search "AuthService" .',
    label: "synap search",
    description: "Executes hybrid lexical, structural, and semantic code retrieval in 9.2ms.",
    logs: [
      { text: '❯ synap search "AuthService" .', type: "cmd" },
      { text: "› Intent: EXACT_SYMBOL | Latency: 9.2ms", type: "info" },
      { text: "★ AST Matches in src/auth/service.py:", type: "title" },
      { text: "  • class AuthService (lines 14-92) [sha256: e82f1b]", type: "success" },
      { text: "  • def verify_jwt(token: str) -> Claims (lines 45-56)", type: "success" },
      { text: "› Inbound Callers (3): api/routes/login.py, middleware/auth.py", type: "info" },
      { text: "› Grounded tokens provided: 340 (avoided 45,000 raw tokens)", type: "success" }
    ]
  },
  {
    id: "watch",
    cmd: "synap status --watch",
    label: "synap status -w",
    description: "Live terminal dashboard monitoring indexing state and daemon parameters in real-time.",
    logs: [
      { text: "❯ synap status --watch", type: "cmd" },
      { text: "Synapse Live Runtime Monitor (Press 'q' to exit)", type: "title" },
      { text: "  Daemon Status: ACTIVE (PID 14455, Port 9876)", type: "success" },
      { text: "  Active Branch: main | Commit: 40cba4b", type: "info" },
      { text: "  Indexed Files: 1,120 | Total Symbols: 8,421 | Edges: 14,290", type: "info" },
      { text: "  Wiki Pages: 14 Fresh (0 Stale, 0 Pending)", type: "success" },
      { text: "  Avg Retrieval Latency: 9.2ms | SQLite WAL Size: 1.8 MB", type: "success" }
    ]
  },
  {
    id: "doctor",
    cmd: "synap doctor .",
    label: "synap doctor",
    description: "Runs system diagnostics on database integrity, parsers, and provider health.",
    logs: [
      { text: "❯ synap doctor .", type: "cmd" },
      { text: "Synap Doctor: System Health Check", type: "title" },
      { text: "  ✓ Database integrity: ok (.synap/synap.db WAL)", type: "success" },
      { text: "  ✓ Tree-sitter parsers functional (py, ts, rs, go, c, cpp)", type: "success" },
      { text: "  ✓ Tokenizer (tiktoken) ready", type: "success" },
      { text: "  ✓ Git and GitHub CLI installed", type: "success" },
      { text: "  ✓ Provider (ollama) connectivity verified on 127.0.0.1:11434", type: "success" },
      { text: "All checks complete.", type: "success" }
    ]
  },
  {
    id: "cost",
    cmd: "synap cost .",
    label: "synap cost",
    description: "Renders aggregated LLM token usage, call logs, and estimated USD cost.",
    logs: [
      { text: "❯ synap cost .", type: "cmd" },
      { text: "LLM Call Aggregated Usage & Cost Summary", type: "title" },
      { text: "  Provider: ollama | Model: qwen2.5-coder:14b | Purpose: wiki", type: "info" },
      { text: "  Calls: 48 | Input Tokens: 64,200 | Output Tokens: 12,400", type: "info" },
      { text: "  Total Estimated Cost: $0.0000 (100% Localhost Savings)", type: "success" }
    ]
  }
]

export function CliPlayground() {
  const [activeSpec, setActiveSpec] = useState<CommandSpec>(CLI_SPECS[0])
  const [copied, setCopied] = useState(false)

  const copyCommand = () => {
    navigator.clipboard.writeText(activeSpec.cmd)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section id="cli" className="py-20 bg-surface-subtle/20 border-b border-border-subtle">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="max-w-3xl mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-text-secondary text-xs font-mono mb-4">
            <TerminalIcon className="w-3.5 h-3.5 text-accent-blue" />
            <span>Interactive CLI Reference</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary tracking-tight">
            Designed for Developers & Daemons.
          </h2>
          <p className="mt-3 text-text-secondary font-sans text-sm sm:text-base leading-relaxed">
            Every feature in Synapse is accessible through a high-performance Typer CLI. Test the subcommands below to inspect actual terminal output.
          </p>
        </div>

        {/* Command Browser & Terminal Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

          {/* Left Command List */}
          <div className="lg:col-span-4 space-y-2 font-mono text-xs">
            {CLI_SPECS.map(spec => (
              <button
                key={spec.id}
                onClick={() => setActiveSpec(spec)}
                className={`w-full text-left p-3.5 rounded-xl border transition-all flex items-center justify-between cursor-pointer ${
                  activeSpec.id === spec.id
                    ? "bg-surface-hover border-accent-blue/50 text-text-primary font-medium shadow-md"
                    : "bg-surface/50 border-border text-text-secondary hover:border-border-strong hover:bg-surface"
                }`}
              >
                <div>
                  <span className="font-semibold">{spec.label}</span>
                  <p className="text-[11px] text-text-muted mt-0.5 line-clamp-1 font-sans">
                    {spec.description}
                  </p>
                </div>
                <Play className={`w-3 h-3 ${activeSpec.id === spec.id ? "text-accent-blue fill-accent-blue" : "text-text-muted"}`} />
              </button>
            ))}
          </div>

          {/* Right Terminal Window */}
          <div className="lg:col-span-8 minimal-card overflow-hidden font-mono text-xs shadow-2xl">
            {/* Terminal Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-subtle">
              <div className="flex items-center gap-2">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#ef4444]/60"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]/60"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-[#10b981]/60"></div>
                </div>
                <span className="text-xs text-text-muted ml-2">zsh — {activeSpec.cmd}</span>
              </div>

              <button
                onClick={copyCommand}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface border border-border text-text-muted hover:text-text-primary transition-all cursor-pointer text-[11px]"
              >
                {copied ? <Check className="w-3 h-3 text-accent-emerald" /> : <Copy className="w-3 h-3" />}
                <span>{copied ? "Copied" : "Copy Command"}</span>
              </button>
            </div>

            {/* Terminal Log Output */}
            <div className="p-5 bg-[#08090D] min-h-[300px] flex flex-col justify-start space-y-2 text-[12px] leading-relaxed">
              {activeSpec.logs.map((log, i) => (
                <div
                  key={i}
                  className={`${
                    log.type === "cmd"
                      ? "text-accent-blue font-bold pb-1"
                      : log.type === "title"
                      ? "text-text-primary font-bold pt-1"
                      : log.type === "success"
                      ? "text-accent-emerald"
                      : log.type === "warning"
                      ? "text-accent-amber"
                      : "text-text-secondary"
                  }`}
                >
                  {log.text}
                </div>
              ))}
              <div className="flex items-center gap-2 text-text-muted pt-2">
                <span className="text-accent-blue">❯</span>
                <span className="w-2 h-4 bg-accent-blue animate-blink inline-block"></span>
              </div>
            </div>
          </div>

        </div>

      </div>
    </section>
  )
}
