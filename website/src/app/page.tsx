"use client"

import React, { useState, useEffect } from "react"
import Link from "next/link"
import { motion, AnimatePresence } from "framer-motion"
import {
  Terminal as TerminalIcon,
  Cpu,
  Database,
  Layers,
  Check,
  ArrowRight,
  BookOpen,
  Zap,
  Shield,
  Code,
  Network,
  Maximize2,
  Copy,
  ChevronRight
} from "lucide-react"
import { BrowserWindow } from "@/components/ui/browser-window"

// Preset CLI commands and their simulated output
const CLI_COMMANDS = [
  {
    name: "synap init",
    description: "Initialize Synap indexer in project root",
    logs: [
      { text: "❯ synap init .", type: "cmd" },
      { text: "✔ Initialized Synap runtime environment in .synap/", type: "success" },
      { text: "✔ SQLite database created at .synap/synap.db", type: "info" },
      { text: "✔ Loaded 25+ language grammar parsers", type: "info" },
      { text: "ℹ Ready for first repository scan. Run `synap start` next.", type: "warning" }
    ]
  },
  {
    name: "synap start",
    description: "Spawn daemon and index files",
    logs: [
      { text: "❯ synap start .", type: "cmd" },
      { text: "✔ Spawning detached background daemon process...", type: "success" },
      { text: "✔ Synap daemon started (PID 22926)", type: "success" },
      { text: "› Scanning workspace: 1,120 source files found", type: "info" },
      { text: "› Parsing structures with Tree-sitter [████████████████] 100% (452ms)", type: "info" },
      { text: "› Building symbol graph & database edges...", type: "info" },
      { text: "✔ Local-first index successfully built. 8,421 symbols resolved.", type: "success" },
      { text: "✔ Diagnostic UI launched at http://127.0.0.1:9876", type: "success" }
    ]
  },
  {
    name: "synap search",
    description: "Query repository structure locally",
    logs: [
      { text: "❯ synap search . \"AuthService\"", type: "cmd" },
      { text: "› Query resolved in 4.8ms via SQLite FTS5 index", type: "info" },
      { text: "★ matches found in src/auth/service.py:", type: "info" },
      { text: "  • Class: AuthService (lines 12-85) [score: 0.98]", type: "success" },
      { text: "  • Method: AuthService.verify_token (lines 45-52) [score: 0.89]", type: "success" },
      { text: "  • Import: from jose import jwt (line 3) [score: 0.76]", type: "success" },
      { text: "✔ Structural context retrieved. Token count: 420.", type: "success" }
    ]
  },
  {
    name: "synap doctor",
    description: "Diagnose system health",
    logs: [
      { text: "❯ synap doctor .", type: "cmd" },
      { text: "Synap Doctor: System Health Check", type: "title" },
      { text: "  ✔ Database integrity: OK", type: "success" },
      { text: "  ✔ Tree-sitter parsers functional", type: "success" },
      { text: "  ✔ Tokenizer (tiktoken) ready", type: "success" },
      { text: "  ✔ Git and GitHub CLI installed", type: "success" },
      { text: "  ✔ Daemon status: ACTIVE & HEALTHY (PID 22926)", type: "success" },
      { text: "✔ All checks complete. Environment is perfectly stable.", type: "success" }
    ]
  }
]

// Mock Token Budgeting dataset
const SEARCH_BUDGET_DATA = [
  {
    symbol: "class DatabaseConnection",
    tokens: 150,
    importance: "critical",
    category: "definition",
    code: `class DatabaseConnection:
    """Manages SQLite pool and WAL configuration."""
    def __init__(self, path: Path):
        self.path = path
        self.pool = sqlite3.connect(path)`
  },
  {
    symbol: "def execute(self, query, params)",
    tokens: 280,
    importance: "high",
    category: "methods",
    code: `    def execute(self, query: str, params: tuple = ()) -> list:
        with self.pool:
            cursor = self.pool.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()`
  },
  {
    symbol: "def check_health(self)",
    tokens: 180,
    importance: "medium",
    category: "methods",
    code: `    def check_health(self) -> bool:
        try:
            self.execute("SELECT 1")
            return True
        except Exception:
            return False`
  },
  {
    symbol: "import sqlite3",
    tokens: 30,
    importance: "low",
    category: "imports",
    code: `import sqlite3
from pathlib import Path`
  },
  {
    symbol: "def close(self)",
    tokens: 90,
    importance: "low",
    category: "cleanup",
    code: `    def close(self):
        self.pool.close()`
  }
]

export default function Home() {
  // Console tab state
  const [activeConsoleIndex, setActiveConsoleIndex] = useState(0)
  const [typedLogs, setTypedLogs] = useState<any[]>([])
  const [isTyping, setIsTyping] = useState(false)

  // Token budgeting simulator state
  const [tokenBudget, setTokenBudget] = useState(400) // slider value

  // Copy helper
  const [copiedText, setCopiedText] = useState<string | null>(null)

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedText(text)
    setTimeout(() => setCopiedText(null), 2000)
  }

  // Trigger terminal typing simulation on activeConsoleIndex change
  useEffect(() => {
    const fullLogs = CLI_COMMANDS[activeConsoleIndex].logs
    setTypedLogs([])
    setIsTyping(true)

    let currentLogIndex = 0
    const interval = setInterval(() => {
      if (currentLogIndex < fullLogs.length) {
        setTypedLogs(prev => [...prev, fullLogs[currentLogIndex]])
        currentLogIndex++
      } else {
        setIsTyping(false)
        clearInterval(interval)
      }
    }, 120)

    return () => clearInterval(interval)
  }, [activeConsoleIndex])

  // Compute retrieved items under the token budget
  let accumulatedTokens = 0
  const retrievedItems = SEARCH_BUDGET_DATA.map(item => {
    accumulatedTokens += item.tokens
    const included = accumulatedTokens <= tokenBudget
    return { ...item, included, runningTotal: accumulatedTokens }
  })

  const totalUsedTokens = retrievedItems.reduce((acc, item) => item.included ? acc + item.tokens : acc, 0)

  return (
    <div className="relative min-h-screen bg-zinc-950 text-zinc-100 font-sans selection:bg-zinc-800 selection:text-zinc-250 overflow-x-hidden antialiased">

      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-zinc-900 bg-zinc-950/80 backdrop-blur-md">
        <div className="flex h-16 max-w-7xl items-center justify-between px-6 md:px-8 mx-auto">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded bg-zinc-900 flex items-center justify-center border border-zinc-800 shadow">
              <Cpu className="h-4.5 w-4.5 text-zinc-200" />
            </div>
            <span className="font-display font-bold text-lg tracking-tight text-zinc-100">Synap</span>
          </div>

          <nav className="hidden md:flex items-center gap-8">
            <Link href="#how-it-works" className="text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-zinc-100 transition-colors">How it works</Link>
            <Link href="#architecture" className="text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-zinc-100 transition-colors">Architecture</Link>
            <Link href="#budgeting" className="text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-zinc-100 transition-colors">Token Budgeting</Link>
            <Link href="#pricing" className="text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-zinc-100 transition-colors">Pricing</Link>
            <Link href="/docs" className="text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-zinc-100 transition-colors">Docs</Link>
          </nav>

          <div className="flex items-center gap-4">
            <a
              href="https://github.com/saahilpal/synapse"
              target="_blank"
              rel="noopener noreferrer"
              className="text-zinc-400 hover:text-zinc-100 transition-colors"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
              </svg>
            </a>
            <Link
              href="/docs"
              className="hidden sm:inline-flex items-center gap-1.5 rounded bg-zinc-100 px-4 py-2 text-xs font-bold text-zinc-950 hover:bg-zinc-200 active:scale-[0.98] transition-all"
            >
              Get Started
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative pt-24 pb-20 md:pt-32 md:pb-32 px-6 md:px-8 max-w-6xl mx-auto flex flex-col items-center text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/40 px-3 py-1 text-[10px] font-mono tracking-wider text-zinc-400 uppercase mb-8">
          Local-First · Deterministic · Instant
        </div>

        <h1 className="font-display font-bold text-4xl sm:text-6xl tracking-tight max-w-4xl text-zinc-100 mb-8 leading-[1.1]">
          The Semantic Context Engine Built for AI Coding Agents
        </h1>

        <p className="text-base sm:text-lg text-zinc-400 max-w-2xl leading-relaxed mb-10">
          Synap parses your entire repository using Tree-sitter, indexes code structures locally inside a SQLite FTS5 database, and serves high-fidelity context to IDE agents in under 10ms.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center items-center w-full max-w-md mb-20">
          <div className="flex items-center justify-between w-full rounded border border-zinc-800 bg-zinc-900/50 px-4 py-3 font-mono text-xs text-zinc-300">
            <span>pip install synap-git</span>
            <button
              onClick={() => handleCopy("pip install synap-git")}
              className="text-zinc-500 hover:text-zinc-300 transition-colors ml-4 focus:outline-none"
            >
              {copiedText === "pip install synap-git" ? <Check className="h-4 w-4 text-zinc-400" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
          <Link
            href="/docs"
            className="flex items-center justify-center gap-2 w-full sm:w-auto shrink-0 bg-zinc-100 hover:bg-zinc-200 text-zinc-950 font-bold px-6 py-3 rounded active:scale-95 transition-all text-xs"
          >
            Start Indexing
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        {/* Feature Highlights */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 w-full border-t border-zinc-900 pt-12 text-left">
          {[
            { title: "25+ Languages", desc: "Native parsing with custom AST rules" },
            { title: "<10ms Query Latency", desc: "SQLite FTS5 indexed search" },
            { title: "100% Local Execution", desc: "Your code never leaves your computer" },
            { title: "MCP Protocol", desc: "Native Cursor & Windsurf integration" }
          ].map((item, i) => (
            <div key={i} className="space-y-1">
              <div className="text-sm font-semibold text-zinc-100">{item.title}</div>
              <div className="text-xs text-zinc-500">{item.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* CLI terminal widget */}
      <section id="how-it-works" className="py-20 md:py-24 px-6 md:px-8 border-t border-zinc-900 bg-zinc-950/20">
        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">

          <div className="lg:col-span-5 space-y-6">
            <div className="text-xs font-mono uppercase tracking-wider text-zinc-500">Interactive CLI Explorer</div>
            <h2 className="font-display font-bold text-2xl sm:text-3xl text-zinc-100 tracking-tight leading-snug">
              One client to configure, index, and repair
            </h2>
            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
              Synap abstracts index building, daemon management, and system status behind a lightweight CLI interface.
            </p>

            <div className="space-y-2 pt-2">
              {CLI_COMMANDS.map((cmd, i) => (
                <button
                  key={cmd.name}
                  onClick={() => setActiveConsoleIndex(i)}
                  className={`w-full text-left p-3.5 rounded border transition-all duration-200 flex items-center justify-between ${
                    activeConsoleIndex === i
                    ? "bg-zinc-900 border-zinc-700 text-zinc-100"
                    : "bg-zinc-950/20 border-zinc-900 hover:border-zinc-800 text-zinc-400"
                  }`}
                >
                  <div>
                    <div className="font-mono text-xs font-bold text-zinc-200">{cmd.name}</div>
                    <div className="text-[11px] text-zinc-500 mt-1">{cmd.description}</div>
                  </div>
                  <ChevronRight className={`h-3.5 w-3.5 transition-transform ${activeConsoleIndex === i ? "translate-x-0.5 text-zinc-300" : "text-zinc-600"}`} />
                </button>
              ))}
            </div>
          </div>

          <div className="lg:col-span-7">
            <BrowserWindow className="h-[380px]" url="localhost:3000/terminal">
              <div className="p-5 font-mono text-xs leading-relaxed overflow-y-auto h-full flex flex-col justify-between bg-zinc-950">
                <div className="space-y-1.5">
                  <AnimatePresence>
                    {typedLogs.map((log, index) => (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ duration: 0.1 }}
                        className={`${
                          log.type === "cmd" ? "text-zinc-100 font-bold" :
                          log.type === "success" ? "text-zinc-300" :
                          log.type === "warning" ? "text-zinc-400" :
                          log.type === "info" ? "text-zinc-500" :
                          log.type === "title" ? "text-zinc-100 font-extrabold border-b border-zinc-900 pb-1 mb-2" :
                          "text-zinc-600"
                        }`}
                      >
                        {log.text}
                      </motion.div>
                    ))}
                  </AnimatePresence>

                  {isTyping && (
                    <div className="inline-block h-3.5 w-1.5 bg-zinc-400 animate-blink align-middle ml-1" />
                  )}
                </div>
                <div className="text-zinc-600 text-[10px] mt-6 pt-3 border-t border-zinc-900 flex justify-between">
                  <span>DAEMON ACTIVE: PID 22926</span>
                  <span>v2.1.7</span>
                </div>
              </div>
            </BrowserWindow>
          </div>

        </div>
      </section>

      {/* Tech Under the Hood / Architecture */}
      <section id="architecture" className="py-20 md:py-24 px-6 md:px-8 border-t border-zinc-900 bg-zinc-950">
        <div className="max-w-6xl mx-auto">

          <div className="max-w-2xl mb-16 space-y-3">
            <div className="text-xs font-mono uppercase tracking-wider text-zinc-500">Technical Architecture</div>
            <h2 className="font-display font-bold text-2xl sm:text-3xl text-zinc-100 tracking-tight">
              Static Analysis meets Local Semantics
            </h2>
            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
              Synap uses pure static analysis to resolve relationships in your codebase without relying on external cloud processing.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">

            {/* Step 1: AST */}
            <div className="rounded border border-zinc-900 bg-zinc-950 p-6 flex flex-col justify-between hover:border-zinc-800 transition-all">
              <div className="space-y-3">
                <div className="h-7 w-7 rounded bg-zinc-900 flex items-center justify-center border border-zinc-800 text-zinc-400">
                  <Code className="h-4 w-4" />
                </div>
                <h3 className="font-display font-bold text-base text-zinc-100">1. Tree-sitter Parsing</h3>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Extracts raw source into concrete syntax trees. Synap isolates function declarations, class boundaries, scope levels, and documentation strings.
                </p>
              </div>

              <div className="mt-8 border border-zinc-900 rounded p-3 bg-zinc-900/30 font-mono text-[10px] space-y-1">
                <div className="text-zinc-600"># Node definitions</div>
                <div>class_definition</div>
                <div className="pl-3 text-zinc-500">└─ name: UserManager</div>
                <div className="pl-3">└─ function_definition</div>
                <div className="pl-6 text-zinc-500">└─ name: create_user</div>
              </div>
            </div>

            {/* Step 2: SQLite */}
            <div className="rounded border border-zinc-900 bg-zinc-950 p-6 flex flex-col justify-between hover:border-zinc-800 transition-all">
              <div className="space-y-3">
                <div className="h-7 w-7 rounded bg-zinc-900 flex items-center justify-center border border-zinc-800 text-zinc-400">
                  <Database className="h-4 w-4" />
                </div>
                <h3 className="font-display font-bold text-base text-zinc-100">2. Local SQLite Relational Store</h3>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Saves structural symbols and dependency edges into index tables. Implements FTS5 virtual tables to match queries instantly.
                </p>
              </div>

              <div className="mt-8 border border-zinc-900 rounded p-3 bg-zinc-900/30 font-mono text-[10px] space-y-1.5 text-zinc-400">
                <div className="text-zinc-600"># Database Schema</div>
                <div className="flex justify-between border-b border-zinc-900 pb-1 text-zinc-500">
                  <span>symbols</span>
                  <span>id | name | kind</span>
                </div>
                <div className="flex justify-between text-zinc-500">
                  <span>edges</span>
                  <span>from_id | to_id</span>
                </div>
              </div>
            </div>

            {/* Step 3: MCP */}
            <div className="rounded border border-zinc-900 bg-zinc-950 p-6 flex flex-col justify-between hover:border-zinc-800 transition-all">
              <div className="space-y-3">
                <div className="h-7 w-7 rounded bg-zinc-900 flex items-center justify-center border border-zinc-800 text-zinc-400">
                  <Network className="h-4 w-4" />
                </div>
                <h3 className="font-display font-bold text-base text-zinc-100">3. Model Context Protocol</h3>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Communicates request context back to IDE models via standard JSON-RPC interface. Delivers clean structures directly inside the chat loop.
                </p>
              </div>

              <div className="mt-8 border border-zinc-900 rounded p-3 bg-zinc-900/30 font-mono text-[10px] space-y-1 text-zinc-500">
                <div className="text-zinc-600"># JSON-RPC server response</div>
                <div>{"{"}</div>
                <div className="pl-3">"method": "tools/call",</div>
                <div className="pl-3">"result": {"{ "} "symbols": [...] {"}"}</div>
                <div>{"}"}</div>
              </div>
            </div>

          </div>

        </div>
      </section>

      {/* Token Budgeting Simulator */}
      <section id="budgeting" className="py-20 md:py-24 px-6 md:px-8 border-t border-zinc-900 bg-zinc-950/20">
        <div className="max-w-6xl mx-auto">

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">

            <div className="lg:col-span-5 space-y-6">
              <div className="text-xs font-mono uppercase tracking-wider text-zinc-500">First-Principles Optimization</div>
              <h2 className="font-display font-bold text-2xl sm:text-3xl text-zinc-100 tracking-tight leading-snug">
                Avoid context stuffing. Budget tokens precisely.
              </h2>
              <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
                LLM performance drops when contexts are bloated. Synap ranks code modules by structural importance and dynamically trims text to meet limits.
              </p>

              {/* Slider Controller */}
              <div className="bg-zinc-900 border border-zinc-800 p-5 rounded space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">Token Limit</span>
                  <span className="font-mono text-xs font-bold text-zinc-200">{tokenBudget} tokens</span>
                </div>
                <input
                  type="range"
                  min="100"
                  max="800"
                  value={tokenBudget}
                  onChange={(e) => setTokenBudget(Number(e.target.value))}
                  className="w-full h-1 bg-zinc-800 rounded appearance-none cursor-pointer accent-zinc-100"
                />
                <div className="flex justify-between text-[10px] font-mono text-zinc-500">
                  <span>100t (Min)</span>
                  <span>400t (Optimal)</span>
                  <span>800t (Max)</span>
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-2 gap-4 text-center">
                <div className="border border-zinc-900 bg-zinc-950 p-4 rounded">
                  <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Used Tokens</div>
                  <div className="text-xl font-bold text-zinc-200 mt-1 font-mono">{totalUsedTokens}t</div>
                </div>
                <div className="border border-zinc-900 bg-zinc-950 p-4 rounded">
                  <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Retrieved Blocks</div>
                  <div className="text-xl font-bold text-zinc-200 mt-1 font-mono">
                    {retrievedItems.filter(item => item.included).length} / {retrievedItems.length}
                  </div>
                </div>
              </div>
            </div>

            <div className="lg:col-span-7">
              <BrowserWindow className="h-[440px]" url="localhost:3000/context-budget">
                <div className="p-5 h-full flex flex-col justify-between bg-zinc-950">
                  <div className="space-y-3 overflow-y-auto flex-1 pr-1">

                    {retrievedItems.map((item, index) => (
                      <div
                        key={index}
                        className={`p-3 rounded border transition-all duration-200 ${
                          item.included
                          ? "bg-zinc-900/50 border-zinc-800 text-zinc-200"
                          : "border-zinc-950 bg-zinc-950/10 text-zinc-600 opacity-30"
                        }`}
                      >
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-mono text-xs font-bold">{item.symbol}</span>
                          <span className="font-mono text-[10px] text-zinc-500">
                            {item.tokens}t
                          </span>
                        </div>
                        {item.included && (
                          <pre className="font-mono text-[10px] text-zinc-500 bg-zinc-950 p-2 rounded border border-zinc-900 overflow-x-auto mt-2 leading-relaxed">
                            {item.code}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="text-[10px] font-mono text-zinc-500 border-t border-zinc-900 pt-3 flex justify-between items-center mt-3">
                    <span>Limit: {tokenBudget}t</span>
                    <span className="font-bold text-zinc-300">Assembled: {totalUsedTokens}t</span>
                  </div>
                </div>
              </BrowserWindow>
            </div>

          </div>

        </div>
      </section>

      {/* Feature Grid */}
      <section className="py-20 md:py-24 px-6 md:px-8 border-t border-zinc-900 bg-zinc-950">
        <div className="max-w-6xl mx-auto">

          <div className="mb-16 space-y-3">
            <div className="text-xs font-mono uppercase tracking-wider text-zinc-500">Features</div>
            <h2 className="font-display font-bold text-2xl sm:text-3xl text-zinc-100 tracking-tight">
              Designed for performance and security
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: <Zap className="h-4 w-4" />,
                title: "Incremental Updates",
                desc: "Synap indexes only modified files, keeping updates under 50ms upon file saves."
              },
              {
                icon: <Code className="h-4 w-4" />,
                title: "Structural Scope Extraction",
                desc: "Resolves full symbol hierarchies instead of matching plain text strings blindly."
              },
              {
                icon: <Shield className="h-4 w-4" />,
                title: "Local Execution",
                desc: "No cloud telemetry or external network calls. Safe for private codebases."
              },
              {
                icon: <Layers className="h-4 w-4" />,
                title: "Memory Graph Integration",
                desc: "Maintains cross-session knowledge structures for reliable context recall."
              },
              {
                icon: <BookOpen className="h-4 w-4" />,
                title: "Lesson Logs",
                desc: "Persists developer patterns to guide models in project conventions."
              },
              {
                icon: <Maximize2 className="h-4 w-4" />,
                title: "Lightweight Footprint",
                desc: "Under 120MB memory utilization during live workspace watch daemon."
              }
            ].map((feat, index) => (
              <div key={index} className="p-6 rounded border border-zinc-900 bg-zinc-950 hover:border-zinc-800 transition-all space-y-3">
                <div className="h-8 w-8 rounded bg-zinc-900 flex items-center justify-center border border-zinc-800 text-zinc-400">
                  {feat.icon}
                </div>
                <h3 className="font-display font-bold text-sm text-zinc-100">{feat.title}</h3>
                <p className="text-xs text-zinc-400 leading-relaxed">{feat.desc}</p>
              </div>
            ))}
          </div>

        </div>
      </section>

      {/* Comparison Matrix */}
      <section className="py-20 md:py-24 px-6 md:px-8 border-t border-zinc-900 bg-zinc-950/20">
        <div className="max-w-6xl mx-auto">

          <div className="mb-16 text-center space-y-3 max-w-xl mx-auto">
            <div className="text-xs font-mono uppercase tracking-wider text-zinc-500">Comparison</div>
            <h2 className="font-display font-bold text-2xl sm:text-3xl text-zinc-100 tracking-tight">
              Compare context strategies
            </h2>
          </div>

          <div className="border border-zinc-900 rounded bg-zinc-950 overflow-hidden shadow-xl">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs font-mono">
                <thead>
                  <tr className="bg-zinc-900/60 border-b border-zinc-800 text-zinc-400">
                    <th className="p-5 font-sans font-bold text-zinc-300">Feature</th>
                    <th className="p-5 text-zinc-100 font-bold bg-zinc-900/40">Synap Core</th>
                    <th className="p-5">Grep / Ripgrep</th>
                    <th className="p-5">Cloud Indexes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900 text-zinc-400">
                  {[
                    { feat: "Search Latency", synap: "<10ms", grep: "Varies with repo size", cloud: "2s - 15s (network bound)" },
                    { feat: "AST Parsing", synap: "✔ Yes (Deterministic)", grep: "✖ No (Plain string matches)", cloud: "Partial / Limited" },
                    { feat: "Privacy Protection", synap: "✔ 100% Local-first", grep: "✔ 100% Local-first", cloud: "✖ Code sent to cloud servers" },
                    { feat: "RAM footprint", synap: "<120 MB", grep: "Varies", cloud: "None (local client only)" },
                    { feat: "Cross-session Memory", synap: "✔ Yes (Graph database)", grep: "✖ No", cloud: "Varies" }
                  ].map((row, i) => (
                    <tr key={i} className="hover:bg-zinc-900/10 transition-colors">
                      <td className="p-5 font-sans font-medium text-zinc-300">{row.feat}</td>
                      <td className="p-5 font-bold text-zinc-200 bg-zinc-900/20">{row.synap}</td>
                      <td className="p-5 text-zinc-500">{row.grep}</td>
                      <td className="p-5 text-zinc-500">{row.cloud}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </section>

      {/* Pricing / Sale Tiers */}
      <section id="pricing" className="py-20 md:py-24 px-6 md:px-8 border-t border-zinc-900 bg-zinc-950">
        <div className="max-w-6xl mx-auto">

          <div className="text-center max-w-xl mx-auto mb-16 space-y-3">
            <div className="text-xs font-mono uppercase tracking-wider text-zinc-500">Pricing</div>
            <h2 className="font-display font-bold text-2xl sm:text-3xl text-zinc-100 tracking-tight">
              Tiers for developers and enterprise
            </h2>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Synap is fully open-source. For corporate workspaces needing multi-repo sync and logs, we offer enterprise self-hosted plans.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-3xl mx-auto">

            {/* Free */}
            <div className="rounded border border-zinc-900 bg-zinc-950 p-6 flex flex-col justify-between hover:border-zinc-800 transition-all">
              <div className="space-y-6">
                <div>
                  <div className="inline-block rounded bg-zinc-900 border border-zinc-800 px-2 py-0.5 text-[10px] font-mono uppercase text-zinc-400">Community Edition</div>
                  <h3 className="font-display font-bold text-xl text-zinc-100 mt-3">Free Forever</h3>
                  <p className="text-xs text-zinc-500 mt-1">Excellent for individual development and open-source contributions.</p>
                </div>

                <div className="text-3xl font-bold font-display text-zinc-100">
                  $0
                  <span className="text-xs font-normal text-zinc-500"> / forever</span>
                </div>

                <div className="border-t border-zinc-900 pt-6 space-y-3">
                  {[
                    "Apache 2.0 Open Source License",
                    "Parsing support for 25+ languages",
                    "Local SQLite FTS5 database",
                    "Live repository watch daemon",
                    "Model Context Protocol client connection"
                  ].map((feat, i) => (
                    <div key={i} className="flex items-center gap-2.5 text-xs text-zinc-300">
                      <Check className="h-3.5 w-3.5 text-zinc-400 shrink-0" />
                      <span>{feat}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-8">
                <Link
                  href="/docs"
                  className="flex items-center justify-center w-full bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 py-2.5 rounded text-xs font-bold transition-all active:scale-[0.98]"
                >
                  Download Open Source
                </Link>
              </div>
            </div>

            {/* Enterprise */}
            <div className="rounded border border-zinc-700 bg-zinc-900/10 p-6 flex flex-col justify-between hover:border-zinc-600 transition-all relative overflow-hidden shadow-lg">
              <div className="space-y-6">
                <div>
                  <div className="inline-block rounded bg-zinc-900 border border-zinc-800 px-2 py-0.5 text-[10px] font-mono uppercase text-zinc-300">Enterprise</div>
                  <h3 className="font-display font-bold text-xl text-zinc-100 mt-3">Team Plan</h3>
                  <p className="text-xs text-zinc-500 mt-1">For teams needing advanced synchronization, audit logging, and team wiki sync.</p>
                </div>

                <div className="text-3xl font-bold font-display text-zinc-100">
                  $19
                  <span className="text-xs font-normal text-zinc-500"> / user / month</span>
                </div>

                <div className="border-t border-zinc-900 pt-6 space-y-3">
                  {[
                    "Everything in Community Edition",
                    "Multi-repository sync & index sharing",
                    "Workspace security audit logs",
                    "Shared Knowledge Wiki database",
                    "Custom LLM mapping configurations",
                    "Dedicated support channels"
                  ].map((feat, i) => (
                    <div key={i} className="flex items-center gap-2.5 text-xs text-zinc-300">
                      <Check className="h-3.5 w-3.5 text-zinc-200 shrink-0" />
                      <span>{feat}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-8">
                <Link
                  href="/docs"
                  className="flex items-center justify-center w-full bg-zinc-100 hover:bg-zinc-200 text-zinc-950 py-2.5 rounded text-xs font-bold transition-all active:scale-[0.98]"
                >
                  Start 14-Day Free Trial
                </Link>
              </div>
            </div>

          </div>

        </div>
      </section>

      {/* CTA */}
      <section className="py-20 md:py-24 px-6 md:px-8 border-t border-zinc-900 bg-zinc-950/20 text-center">
        <div className="max-w-3xl mx-auto space-y-6">
          <h2 className="font-display font-bold text-3xl text-zinc-100 tracking-tight leading-snug">
            Configure structural codebase context today.
          </h2>
          <p className="text-xs sm:text-sm text-zinc-400 max-w-lg mx-auto leading-relaxed">
            Synap takes less than 2 minutes to initialize. Plug it into Cursor, Windsurf, or Claude Desktop to start indexing.
          </p>
          <div className="flex flex-col sm:flex-row justify-center items-center gap-3">
            <Link
              href="/docs"
              className="flex items-center justify-center gap-2 bg-zinc-100 hover:bg-zinc-200 text-zinc-950 font-bold px-6 py-3 rounded active:scale-95 transition-all text-xs"
            >
              Get Started for Free
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <a
              href="https://github.com/saahilpal/synapse"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 px-6 py-3 rounded text-xs font-bold transition-all active:scale-[0.98]"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
              </svg>
              View on GitHub
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-900 bg-zinc-950 py-12 px-6 md:px-8">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-6 text-xs text-zinc-500">
          <div className="flex items-center gap-2.5">
            <div className="h-6 w-6 rounded bg-zinc-900 flex items-center justify-center border border-zinc-800 text-zinc-400">
              <Cpu className="h-3.5 w-3.5" />
            </div>
            <span className="font-display font-bold text-sm text-zinc-200 tracking-tight">Synap</span>
          </div>

          <div className="flex flex-wrap gap-6 font-mono uppercase tracking-wider">
            <Link href="/docs" className="hover:text-zinc-300 transition-colors">Documentation</Link>
            <Link href="/docs/architecture" className="hover:text-zinc-300 transition-colors">Architecture</Link>
            <a href="https://github.com/saahilpal/synapse" target="_blank" rel="noopener noreferrer" className="hover:text-zinc-300 transition-colors">GitHub</a>
          </div>

          <div className="font-mono">
            © 2026 Synap. Apache-2.0 License.
          </div>
        </div>
      </footer>

    </div>
  )
}
