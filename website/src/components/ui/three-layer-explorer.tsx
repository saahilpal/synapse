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
  Database,
  GitCommit,
  ShieldCheck,
  Zap
} from "lucide-react"

export function ThreeLayerExplorer() {
  const [activeLayer, setActiveLayer] = useState<"L1" | "L2" | "L3">("L1")

  return (
    <section id="layers" className="py-20 bg-surface-subtle/30 border-b border-border-subtle relative">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-xs font-mono text-text-secondary mb-3">
            <Layers className="w-3.5 h-3.5 text-accent-blue" />
            <span>3-Layer Context Architecture</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-bold text-text-primary tracking-tight">
            Decoupled Grounding Framework.
          </h2>
          <p className="mt-4 text-text-secondary text-sm sm:text-base font-sans leading-relaxed">
            Synapse decouples deterministic AST graph truth from asynchronous semantic digests and long-term agent memory. Each layer solves a specific failure mode in AI coding workflows.
          </p>
        </div>

        {/* Layer Selector Tabs */}
        <div className="flex justify-center mb-10">
          <div className="inline-flex p-1 rounded-xl bg-surface border border-border font-mono text-xs shadow-md">
            <button
              onClick={() => setActiveLayer("L1")}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-all cursor-pointer ${
                activeLayer === "L1"
                  ? "bg-surface-hover text-accent-blue font-semibold border border-border"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              <Code2 className="w-3.5 h-3.5 text-accent-blue" />
              <span>L1: Structural Code Graph</span>
            </button>

            <button
              onClick={() => setActiveLayer("L2")}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-all cursor-pointer ${
                activeLayer === "L2"
                  ? "bg-surface-hover text-accent-emerald font-semibold border border-border"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              <BookOpen className="w-3.5 h-3.5 text-accent-emerald" />
              <span>L2: Semantic Wiki</span>
            </button>

            <button
              onClick={() => setActiveLayer("L3")}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-all cursor-pointer ${
                activeLayer === "L3"
                  ? "bg-surface-hover text-accent-amber font-semibold border border-border"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              <Brain className="w-3.5 h-3.5 text-accent-amber" />
              <span>L3: Behavioral Memory</span>
            </button>
          </div>
        </div>

        {/* Dynamic Layer Content Card */}
        <div className="max-w-5xl mx-auto">
          <AnimatePresence mode="wait">
            {activeLayer === "L1" && (
              <motion.div
                key="L1"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
                className="minimal-card p-6 sm:p-8"
              >
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start font-mono text-xs">
                  <div className="lg:col-span-6 space-y-4">
                    <div className="flex items-center gap-2 text-accent-blue font-semibold text-sm">
                      <Code2 className="w-4 h-4" />
                      <span>L1 — Tree-sitter Structural Graph & Recursive CTEs</span>
                    </div>
                    <p className="text-text-secondary font-sans text-xs sm:text-sm leading-relaxed">
                      L1 indexes raw AST grammar nodes across all major programming languages into local SQLite relational tables. It maps functions, classes, methods, and caller-callee dependency edges with SHA256 content hashes.
                    </p>
                    <div className="space-y-2 pt-2 text-[11px]">
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Zero LLM hallucinations — 100% deterministic AST parsing</span>
                      </div>
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Sub-millisecond Recursive CTE graph traversal in SQLite</span>
                      </div>
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Git OID tagged: changes re-index only altered file deltas</span>
                      </div>
                    </div>
                  </div>

                  <div className="lg:col-span-6 bg-[#090A0F] rounded-xl border border-border p-4 overflow-x-auto text-[11px] leading-relaxed text-text-secondary">
                    <span className="text-text-muted block text-[10px] uppercase mb-2">Recursive Call-Graph Query</span>
                    <pre className="text-accent-blue">
{`WITH RECURSIVE dependency_chain(symbol_id, target_id, depth) AS (
  SELECT source_symbol_id, target_symbol_id, 1
  FROM edges
  WHERE source_symbol_id = 'sym_SynapRuntime'
  UNION ALL
  SELECT e.source_symbol_id, e.target_symbol_id, dc.depth + 1
  FROM edges e
  JOIN dependency_chain dc ON e.source_symbol_id = dc.target_id
  WHERE dc.depth < 4
)
SELECT s.name, s.kind, s.file_id, dc.depth
FROM dependency_chain dc
JOIN symbols s ON dc.target_id = s.symbol_id;`}
                    </pre>
                  </div>
                </div>
              </motion.div>
            )}

            {activeLayer === "L2" && (
              <motion.div
                key="L2"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
                className="minimal-card p-6 sm:p-8"
              >
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start font-mono text-xs">
                  <div className="lg:col-span-6 space-y-4">
                    <div className="flex items-center gap-2 text-accent-emerald font-semibold text-sm">
                      <BookOpen className="w-4 h-4" />
                      <span>L2 — Asynchronous Semantic Wiki</span>
                    </div>
                    <p className="text-text-secondary font-sans text-xs sm:text-sm leading-relaxed">
                      L2 maintains human-readable markdown summaries of files, modules, and project architecture under <code className="text-text-primary bg-surface px-1 py-0.5 rounded">.synap/wiki/</code>. A background queue regenerates stale summaries when files change, never blocking your interactive coding agent.
                    </p>
                    <div className="space-y-2 pt-2 text-[11px]">
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Instant architectural orientation for agents without reading whole repo</span>
                      </div>
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Background worker queue (`synap wiki retry` / auto-daemon)</span>
                      </div>
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Local Ollama support with 0 token spend on localhost</span>
                      </div>
                    </div>
                  </div>

                  <div className="lg:col-span-6 bg-[#090A0F] rounded-xl border border-border p-4 overflow-x-auto text-[11px] leading-relaxed text-text-secondary">
                    <span className="text-text-muted block text-[10px] uppercase mb-2">Sample L2 Wiki Page (.synap/wiki/overview.md)</span>
                    <pre className="text-accent-emerald">
{`# Module: retrieval/engine.py

## Overview
Coordinates deterministic AST symbol resolution and hybrid
lexical/semantic vector rankings.

## Key Exports
- query_hybrid(query, repo_path, synthesize_answer=False)
- _classify_intent_fast(query) -> RetrievalIntent

## Dependencies
- storage/sqlite.py (WAL queries)
- parser/registry.py (Grammar symbols)`}
                    </pre>
                  </div>
                </div>
              </motion.div>
            )}

            {activeLayer === "L3" && (
              <motion.div
                key="L3"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
                className="minimal-card p-6 sm:p-8"
              >
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start font-mono text-xs">
                  <div className="lg:col-span-6 space-y-4">
                    <div className="flex items-center gap-2 text-accent-amber font-semibold text-sm">
                      <Brain className="w-4 h-4" />
                      <span>L3 — Long-Term Behavioral Memory & Revert Lessons</span>
                    </div>
                    <p className="text-text-secondary font-sans text-xs sm:text-sm leading-relaxed">
                      L3 persists agent progress across sessions. When git reverts or failed tests occur, Synap automatically extracts structured lessons into SQLite, preventing future AI agents from repeating the same architectural mistakes.
                    </p>
                    <div className="space-y-2 pt-2 text-[11px]">
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Automatic revert lesson extraction from git commit history</span>
                      </div>
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Interactive checkpoints (`synap checkpoint create / restore`)</span>
                      </div>
                      <div className="flex items-center gap-2 text-text-secondary">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>Cross-session constraint injection for Cursor and Claude Code</span>
                      </div>
                    </div>
                  </div>

                  <div className="lg:col-span-6 bg-[#090A0F] rounded-xl border border-border p-4 overflow-x-auto text-[11px] leading-relaxed text-text-secondary">
                    <span className="text-text-muted block text-[10px] uppercase mb-2">Auto-Extracted Revert Lesson Payload</span>
                    <pre className="text-accent-amber">
{`{
  "lesson_id": "les_a901ff2b",
  "trigger": "git_revert: commit 4e2a1b",
  "rule": "Do not remove --python flag in uv pip invocations",
  "rationale": "When invoked outside .venv root directory, uv fails unless target python binary is passed explicitly.",
  "status": "approved",
  "injected_into_mcp_context": true
}`}
                    </pre>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

      </div>
    </section>
  )
}
