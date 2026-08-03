"use client"

import React, { useState, useEffect } from "react"
import {
  Terminal as TerminalIcon,
  Check,
  Copy
} from "lucide-react"

interface CommandSpec {
  id: string
  cmd: string
  label: string
  description: string
  logs: { text: string; type: "cmd" | "info" | "success" | "warning" | "title" }[]
}

const CLI_SPECS: CommandSpec[] = [
  {
    id: "setup",
    cmd: "synap setup .",
    label: "synap setup",
    description: "Interactive first-run configuration and onboarding.",
    logs: [
      { text: "❯ synap setup .", type: "cmd" },
      { text: "Synap AI Engine Setup & Onboarding", type: "title" },
      { text: "✔ Verifying Git repository root...", type: "success" },
      { text: "✔ Loaded 25+ language grammar parsers (Tree-sitter)", type: "info" },
      { text: "✔ Created .synap/ configuration directory", type: "info" },
      { text: "✔ Initialized SQLite WAL database at .synap/synap.db", type: "success" },
      { text: "✔ Environment ready. Run `synap start` to launch daemon.", type: "success" }
    ]
  },
  {
    id: "start",
    cmd: "synap start .",
    label: "synap start",
    description: "Spawn detached background runtime daemon process.",
    logs: [
      { text: "❯ synap start .", type: "cmd" },
      { text: "✔ Spawning detached background daemon process...", type: "success" },
      { text: "✔ Synap daemon started (PID 22926)", type: "success" },
      { text: "› Scanning workspace: 1,120 source files found", type: "info" },
      { text: "› Parsing structures with Tree-sitter [████████████████] 100% (452ms)", type: "info" },
      { text: "› Building symbol graph & database edges...", type: "info" },
      { text: "✔ Local-first index successfully built. 8,421 symbols resolved.", type: "success" },
      { text: "✔ REST API & Dashboard active at http://127.0.0.1:9876", type: "success" }
    ]
  },
  {
    id: "search",
    cmd: "synap search . \"AuthService\"",
    label: "synap search",
    description: "Execute hybrid CTE & FTS5 structural search locally.",
    logs: [
      { text: "❯ synap search . \"AuthService\"", type: "cmd" },
      { text: "› Query resolved in 4.8ms via SQLite FTS5 + Recursive CTE index", type: "info" },
      { text: "★ Matches found in src/auth/service.py:", type: "info" },
      { text: "  • Class: AuthService (lines 12-85) [sha256: 9f81a2e]", type: "success" },
      { text: "  • Method: AuthService.verify_token (lines 45-52)", type: "success" },
      { text: "  • Import: from jose import jwt (line 3)", type: "success" },
      { text: "✔ Structural context packaged. Token count: 420.", type: "success" }
    ]
  },
  {
    id: "doctor",
    cmd: "synap doctor .",
    label: "synap doctor",
    description: "Diagnose system health, database integrity, and daemon status.",
    logs: [
      { text: "❯ synap doctor .", type: "cmd" },
      { text: "Synap Doctor: System Diagnostics", type: "title" },
      { text: "  ✔ Database integrity (WAL mode): OK", type: "success" },
      { text: "  ✔ Tree-sitter parsers (25 languages): FUNCTIONAL", type: "success" },
      { text: "  ✔ Tokenizer (tiktoken budgeter): READY", type: "success" },
      { text: "  ✔ Git repository state: VALID (HEAD: a4f8e91)", type: "success" },
      { text: "  ✔ Daemon process status: ACTIVE & HEALTHY (PID 22926)", type: "success" },
      { text: "✔ All checks complete. Environment is perfectly stable.", type: "success" }
    ]
  }
]

export function CliPlayground() {
  const [selectedId, setSelectedId] = useState<string>("start")
  const [typedLogs, setTypedLogs] = useState<CommandSpec["logs"]>(CLI_SPECS[1].logs)
  const [copied, setCopied] = useState(false)

  const activeSpec = CLI_SPECS.find(s => s.id === selectedId) || CLI_SPECS[1]

  useEffect(() => {
    let currentIdx = 0
    const targetLogs = activeSpec.logs
    const timer = setTimeout(() => {
      setTypedLogs([])
      const interval = setInterval(() => {
        if (currentIdx < targetLogs.length) {
          const item = targetLogs[currentIdx]
          setTypedLogs(prev => [...prev, item])
          currentIdx++
        } else {
          clearInterval(interval)
        }
      }, 90)
    }, 10)

    return () => clearTimeout(timer)
  }, [selectedId, activeSpec])

  const copyCommand = () => {
    navigator.clipboard.writeText(activeSpec.cmd)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section id="cli" className="py-20 bg-slate-950 border-b border-slate-800/80 relative">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300 mb-3">
            <TerminalIcon className="w-3.5 h-3.5 text-sky-400" />
            <span>Developer CLI Tooling</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-bold text-slate-100 tracking-tight">
            Clean Typer Subcommands
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg font-sans">
            Manage repository indexing, daemon processes, and diagnostic health checks directly from your terminal.
          </p>
        </div>

        {/* Terminal Sandbox */}
        <div className="max-w-4xl mx-auto tech-card overflow-hidden shadow-xl">

          {/* Terminal Top Bar */}
          <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-slate-700" />
                <div className="w-3 h-3 rounded-full bg-slate-700" />
                <div className="w-3 h-3 rounded-full bg-slate-700" />
              </div>
              <span className="text-xs font-mono text-slate-400 border-l border-slate-800 pl-3">
                zsh — synap CLI Simulator
              </span>
            </div>

            {/* Command Subcommand Selector Tabs */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {CLI_SPECS.map(spec => (
                <button
                  key={spec.id}
                  onClick={() => setSelectedId(spec.id)}
                  className={`px-3 py-1 rounded-lg text-xs font-mono transition-all ${
                    selectedId === spec.id
                      ? "bg-slate-800 text-sky-400 font-semibold border border-slate-700"
                      : "bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800"
                  }`}
                >
                  {spec.label}
                </button>
              ))}
            </div>
          </div>

          {/* Terminal Console Output Body */}
          <div className="p-6 bg-slate-950 font-mono text-xs text-slate-300 min-h-[300px] flex flex-col justify-between">
            <div className="space-y-2">
              <div className="text-slate-500 text-[11px] pb-2 border-b border-slate-900 flex items-center justify-between">
                <span>{activeSpec.description}</span>
                <button
                  onClick={copyCommand}
                  className="flex items-center gap-1 text-sky-400 hover:underline"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? "Copied" : "Copy Command"}</span>
                </button>
              </div>

              {typedLogs.map((log, idx) => (
                <div key={idx} className="leading-relaxed">
                  {log.type === "cmd" && <span className="text-sky-400 font-bold">{log.text}</span>}
                  {log.type === "title" && <span className="text-slate-100 font-bold underline">{log.text}</span>}
                  {log.type === "info" && <span className="text-slate-400">{log.text}</span>}
                  {log.type === "success" && <span className="text-emerald-400">{log.text}</span>}
                  {log.type === "warning" && <span className="text-amber-400">{log.text}</span>}
                </div>
              ))}
            </div>

            {/* Terminal Cursor Prompt line */}
            <div className="mt-4 pt-3 border-t border-slate-900 flex items-center gap-2 text-slate-400 text-[11px]">
              <span className="text-sky-400 font-bold">❯</span>
              <span className="w-2 h-4 bg-sky-400 animate-blink" />
            </div>

          </div>

        </div>

      </div>
    </section>
  )
}
