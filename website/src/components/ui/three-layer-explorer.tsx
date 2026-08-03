"use client"

import React, { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  Layers,
  Code2,
  BookOpen,
  Brain,
  CheckCircle,
  FileText,
  Clock,
  Terminal,
  ShieldAlert
} from "lucide-react"

export function ThreeLayerExplorer() {
  const [activeLayer, setActiveLayer] = useState<"L1" | "L2" | "L3">("L1")

  return (
    <section id="layers" className="py-20 bg-slate-950 border-b border-slate-800/80 relative">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-700/80 text-xs font-mono text-slate-300 mb-3">
            <Layers className="w-3.5 h-3.5 text-sky-400" />
            <span>The 3-Layer Context Model</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-bold text-slate-100 tracking-tight">
            Decoupled Grounding Framework
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg font-sans">
            Synapse isolates structural AST truth from non-deterministic summaries through three defined layers, ensuring perfect context bounds for AI agents.
          </p>
        </div>

        {/* Layer Selector Tabs */}
        <div className="flex justify-center mb-12">
          <div className="inline-flex p-1.5 rounded-2xl bg-slate-900 border border-slate-800 font-mono text-sm shadow-md">
            <button
              onClick={() => setActiveLayer("L1")}
              className={`px-5 py-2.5 rounded-xl flex items-center gap-2.5 transition-all ${
                activeLayer === "L1"
                  ? "bg-slate-800 text-sky-400 font-semibold border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Code2 className="w-4 h-4 text-sky-400" />
              <span>L1: Structural Graph</span>
            </button>

            <button
              onClick={() => setActiveLayer("L2")}
              className={`px-5 py-2.5 rounded-xl flex items-center gap-2.5 transition-all ${
                activeLayer === "L2"
                  ? "bg-slate-800 text-emerald-400 font-semibold border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <BookOpen className="w-4 h-4 text-emerald-400" />
              <span>L2: Semantic Wiki</span>
            </button>

            <button
              onClick={() => setActiveLayer("L3")}
              className={`px-5 py-2.5 rounded-xl flex items-center gap-2.5 transition-all ${
                activeLayer === "L3"
                  ? "bg-slate-800 text-amber-400 font-semibold border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Brain className="w-4 h-4 text-amber-400" />
              <span>L3: Behavioral Memory</span>
            </button>
          </div>
        </div>

        {/* Dynamic Layer Inspector Content */}
        <AnimatePresence mode="wait">
          {activeLayer === "L1" && (
            <motion.div
              key="L1"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.25 }}
              className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch"
            >
              <div className="lg:col-span-6 tech-card p-7 border border-slate-800 flex flex-col justify-between">
                <div>
                  <div className="inline-block px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-sky-400 text-xs font-mono mb-4">
                    Layer 1 — Deterministic AST Graph
                  </div>
                  <h3 className="text-2xl font-mono font-bold text-slate-100 mb-3">
                    Structural AST Symbol Graph
                  </h3>
                  <p className="text-slate-300 font-sans text-sm leading-relaxed mb-6">
                    L1 parses programming language symbols (classes, functions, methods) via <strong className="text-sky-400">Tree-sitter</strong> and extracts call/import dependency edges into local SQLite graph tables.
                  </p>

                  <div className="space-y-3 font-mono text-xs text-slate-300">
                    <div className="flex items-start gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <CheckCircle className="w-4 h-4 text-sky-400 mt-0.5 shrink-0" />
                      <div>
                        <strong className="text-slate-100">SHA256 Content Keying:</strong>
                        <div className="text-slate-400 text-[11px] mt-0.5">Primary key sha256(path + content_hash) prevents duplication across commits.</div>
                      </div>
                    </div>

                    <div className="flex items-start gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <CheckCircle className="w-4 h-4 text-sky-400 mt-0.5 shrink-0" />
                      <div>
                        <strong className="text-slate-100">SQLite Recursive CTE Traversal:</strong>
                        <div className="text-slate-400 text-[11px] mt-0.5">Expands caller-callee networks up to N depths in single-digit milliseconds.</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-xs font-mono text-sky-400">
                  <span>Source: src/synap_git/parser/registry.py</span>
                  <span>Tree-sitter AST</span>
                </div>
              </div>

              {/* L1 SQLite Schema Card */}
              <div className="lg:col-span-6 tech-card p-6 border border-slate-800 font-mono text-xs flex flex-col justify-between bg-slate-950">
                <div>
                  <div className="text-xs text-slate-400 border-b border-slate-800 pb-2 mb-3 flex items-center justify-between">
                    <span className="text-sky-400 font-semibold">{`// L1 SQLite Graph Schema`}</span>
                    <span className="text-slate-500">.synap/synap.db</span>
                  </div>
                  <pre className="text-slate-300 bg-slate-900 p-4 rounded-xl border border-slate-800 overflow-x-auto text-[11px] leading-relaxed">
{`CREATE TABLE symbols (
    id TEXT PRIMARY KEY,          -- sha256(path + content_hash)
    file_path TEXT NOT NULL,
    symbol_name TEXT NOT NULL,
    kind TEXT NOT NULL,           -- 'class' | 'function' | 'method'
    start_line INTEGER,
    end_line INTEGER
);

CREATE TABLE edges (
    source_id TEXT REFERENCES symbols(id),
    target_id TEXT REFERENCES symbols(id),
    edge_type TEXT NOT NULL       -- 'imports' | 'calls'
);`}
                  </pre>
                </div>
                <div className="mt-4 p-3 rounded-xl bg-slate-900 border border-slate-800 text-[11px] text-sky-300">
                  ✔ 100% deterministic code representation. Zero LLM hallucination.
                </div>
              </div>
            </motion.div>
          )}

          {activeLayer === "L2" && (
            <motion.div
              key="L2"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.25 }}
              className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch"
            >
              <div className="lg:col-span-6 tech-card p-7 border border-slate-800 flex flex-col justify-between">
                <div>
                  <div className="inline-block px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-emerald-400 text-xs font-mono mb-4">
                    Layer 2 — Async Semantic Docs
                  </div>
                  <h3 className="text-2xl font-mono font-bold text-slate-100 mb-3">
                    Semantic Documentation Wiki
                  </h3>
                  <p className="text-slate-300 font-sans text-sm leading-relaxed mb-6">
                    L2 maintains high-level markdown documentation summaries of files, modules, and overall project architecture under <strong className="text-emerald-400">.synap/wiki/</strong>.
                  </p>

                  <div className="space-y-3 font-mono text-xs text-slate-300">
                    <div className="flex items-start gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <Clock className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                      <div>
                        <strong className="text-slate-100">Asynchronous Worker Queue:</strong>
                        <div className="text-slate-400 text-[11px] mt-0.5">Decouples slow LLM summary generation from the fast indexing pipeline.</div>
                      </div>
                    </div>

                    <div className="flex items-start gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <FileText className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                      <div>
                        <strong className="text-slate-100">Lazy Cache Fallback:</strong>
                        <div className="text-slate-400 text-[11px] mt-0.5">Triggers on-demand documentation renders if a missing page is requested.</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-xs font-mono text-emerald-400">
                  <span>Source: src/synap_git/indexer/wiki.py</span>
                  <span>Markdown Wiki</span>
                </div>
              </div>

              {/* L2 Markdown Wiki Preview Card */}
              <div className="lg:col-span-6 tech-card p-6 border border-slate-800 font-mono text-xs flex flex-col justify-between bg-slate-950">
                <div>
                  <div className="text-xs text-slate-400 border-b border-slate-800 pb-2 mb-3 flex items-center justify-between">
                    <span className="text-emerald-400 font-semibold">{`// .synap/wiki/retrieval_engine.md`}</span>
                    <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 rounded border border-emerald-800 text-[10px]">status: fresh</span>
                  </div>
                  <pre className="text-slate-300 bg-slate-900 p-4 rounded-xl border border-slate-800 overflow-x-auto text-[11px] leading-relaxed">
{`# Module: Hybrid Retrieval Engine

## Purpose
Coordinates lexical FTS5 searching with SQLite CTE
graph expansion and tiktoken context budgeting.

## Core Classes
- HybridRetrievalEngine: Executes 4-stage search queries.
- ContextPacker: Truncates context to fit max_tokens.

## Dependents
- mcp/server.py (SynapMCPFacade)
- cli/main.py (synap search subcommand)`}
                  </pre>
                </div>
                <div className="mt-4 p-3 rounded-xl bg-slate-900 border border-slate-800 text-[11px] text-emerald-300">
                  ✔ Human-readable architectural context synced with Git history.
                </div>
              </div>
            </motion.div>
          )}

          {activeLayer === "L3" && (
            <motion.div
              key="L3"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.25 }}
              className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch"
            >
              <div className="lg:col-span-6 tech-card p-7 border border-slate-800 flex flex-col justify-between">
                <div>
                  <div className="inline-block px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-amber-400 text-xs font-mono mb-4">
                    Layer 3 — Agent Memory & Lessons
                  </div>
                  <h3 className="text-2xl font-mono font-bold text-slate-100 mb-3">
                    Behavioral Memory & Revert Lessons
                  </h3>
                  <p className="text-slate-300 font-sans text-sm leading-relaxed mb-6">
                    L3 captures developer-in-the-loop state: active task checkpoints, technical design decisions, and <strong className="text-amber-400">automatic Git revert lessons</strong>.
                  </p>

                  <div className="space-y-3 font-mono text-xs text-slate-300">
                    <div className="flex items-start gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <ShieldAlert className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                      <div>
                        <strong className="text-slate-100">Auto Revert Lesson Extraction:</strong>
                        <div className="text-slate-400 text-[11px] mt-0.5">Detects commit reverts via Git ancestor trees and extracts non-repeating safety rules.</div>
                      </div>
                    </div>

                    <div className="flex items-start gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <Terminal className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                      <div>
                        <strong className="text-slate-100">Checkpoints & Decisions:</strong>
                        <div className="text-slate-400 text-[11px] mt-0.5">Captures &quot;doing&quot;, &quot;changed_files&quot;, &quot;next_step&quot;, and &quot;blockers&quot; across branch swaps.</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-xs font-mono text-amber-400">
                  <span>Source: src/synap_git/git/state.py</span>
                  <span>Persistent Lessons</span>
                </div>
              </div>

              {/* L3 Revert Lesson Memory Preview Card */}
              <div className="lg:col-span-6 tech-card p-6 border border-slate-800 font-mono text-xs flex flex-col justify-between bg-slate-950">
                <div>
                  <div className="text-xs text-slate-400 border-b border-slate-800 pb-2 mb-3 flex items-center justify-between">
                    <span className="text-amber-400 font-semibold">{`// L3 Auto-Extracted Lesson`}</span>
                    <span className="px-2 py-0.5 bg-amber-950 text-amber-300 rounded border border-amber-800 text-[10px]">state: approved</span>
                  </div>
                  <pre className="text-slate-300 bg-slate-900 p-4 rounded-xl border border-slate-800 overflow-x-auto text-[11px] leading-relaxed">
{`{
  "lesson_id": "les_9921a8f",
  "trigger": "git revert commit c3f1a0e",
  "rule": "Never execute blocking SQLite calls on main loop; wrap in asyncio.to_thread()",
  "why_failed": "Asyncio event loop deadlocked during high-frequency AST bulk parsing",
  "injected_into": "System instructions during MCP context packaging"
}`}
                  </pre>
                </div>
                <div className="mt-4 p-3 rounded-xl bg-slate-900 border border-slate-800 text-[11px] text-amber-300">
                  ✔ Learns from past failures and prevents repetitive coding agent mistakes.
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </section>
  )
}
