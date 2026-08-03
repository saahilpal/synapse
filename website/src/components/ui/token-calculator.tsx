"use client"

import React, { useState } from "react"
import {
  Zap,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  Sliders
} from "lucide-react"

export function TokenCalculator() {
  const [locK, setLocK] = useState<number>(50)
  const [queriesPerDay, setQueriesPerDay] = useState<number>(40)

  const rawTokens = Math.round(locK * 1000 * 0.8)
  const vectorRagTokens = Math.round(locK * 1000 * 0.25)
  const synapseTokens = Math.round(Math.min(1800, locK * 30))

  const costPerM = 3.0
  const rawMonthlyCost = Math.round((rawTokens / 1_000_000) * costPerM * queriesPerDay * 22)
  const synapseMonthlyCost = Math.round((synapseTokens / 1_000_000) * costPerM * queriesPerDay * 22)
  const monthlySavings = Math.max(0, rawMonthlyCost - synapseMonthlyCost)

  const tokenReductionPercent = Math.round(((rawTokens - synapseTokens) / rawTokens) * 100)

  return (
    <section id="budgeting" className="py-20 bg-slate-950 border-b border-slate-800/80 relative">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300 mb-3">
            <Zap className="w-3.5 h-3.5 text-sky-400" />
            <span>Token Budgeting Economics</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-bold text-slate-100 tracking-tight">
            Stop Burning Dollars on Context Bloat
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg font-sans">
            Calculate your monthly API cost savings and context window speedups by switching from raw codebase dumps or naive vector embeddings to Synapse.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">

          {/* Controls */}
          <div className="lg:col-span-5 tech-card p-7 border border-slate-800 space-y-6">
            <h3 className="text-lg font-mono font-bold text-slate-100 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-sky-400" />
              Repository Parameters
            </h3>

            <div>
              <div className="flex justify-between items-center text-xs font-mono mb-2">
                <span className="text-slate-400">Codebase Size (Lines of Code):</span>
                <span className="text-sky-400 font-bold text-sm">{locK}k LOC</span>
              </div>
              <input
                type="range"
                min="10"
                max="500"
                step="10"
                value={locK}
                onChange={(e) => setLocK(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-sky-400"
              />
              <div className="flex justify-between text-[10px] font-mono text-slate-500 mt-1">
                <span>10k LOC</span>
                <span>250k LOC</span>
                <span>500k LOC</span>
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center text-xs font-mono mb-2">
                <span className="text-slate-400">Daily Agent Queries per Dev:</span>
                <span className="text-emerald-400 font-bold text-sm">{queriesPerDay} queries</span>
              </div>
              <input
                type="range"
                min="10"
                max="150"
                step="5"
                value={queriesPerDay}
                onChange={(e) => setQueriesPerDay(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-400"
              />
              <div className="flex justify-between text-[10px] font-mono text-slate-500 mt-1">
                <span>10 queries</span>
                <span>80 queries</span>
                <span>150 queries</span>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs text-slate-200 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Token Reduction:</span>
                <span className="text-emerald-400 font-bold text-sm">{tokenReductionPercent}% lower</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Est. Monthly Savings:</span>
                <span className="text-sky-400 font-bold text-base">${monthlySavings} / dev</span>
              </div>
              <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800">
                Calculated at $3.00/1M input tokens (GPT-4o / Claude 3.5 Sonnet benchmark).
              </div>
            </div>

          </div>

          {/* Comparison Cards */}
          <div className="lg:col-span-7 space-y-4">

            {/* Raw Dump */}
            <div className="tech-card p-5 border border-slate-800 bg-slate-900/60">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono font-bold text-amber-400 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4" /> Raw File Context Dumps
                </span>
                <span className="text-xs font-mono text-amber-400 font-bold">~{rawTokens.toLocaleString()} tokens</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px] font-mono text-slate-400 mt-3 pt-3 border-t border-slate-800">
                <div>Est. Cost: <strong className="text-slate-200">${rawMonthlyCost}/mo</strong></div>
                <div>TTFT: <strong className="text-slate-200">18.4s</strong></div>
                <div>Hallucination: <strong className="text-amber-400">High</strong></div>
              </div>
            </div>

            {/* Naive Vector RAG */}
            <div className="tech-card p-5 border border-slate-800 bg-slate-900/60">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono font-bold text-slate-300 flex items-center gap-1.5">
                  <TrendingDown className="w-4 h-4 text-sky-400" /> Naive Vector RAG Embeddings
                </span>
                <span className="text-xs font-mono text-slate-300 font-bold">~{vectorRagTokens.toLocaleString()} tokens</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px] font-mono text-slate-400 mt-3 pt-3 border-t border-slate-800">
                <div>Import Bounds: <strong className="text-amber-400">Lacks Edges</strong></div>
                <div>Class Hierarchy: <strong className="text-amber-400">Missing</strong></div>
                <div>Branch Swaps: <strong className="text-amber-400">Requires Rescan</strong></div>
              </div>
            </div>

            {/* Synapse Engine */}
            <div className="tech-card p-6 border border-sky-500/60 bg-slate-900 shadow-lg ring-1 ring-sky-500/20">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-mono font-bold text-sky-400 flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" /> Synapse Structural Engine
                </span>
                <span className="text-sm font-mono text-sky-300 font-bold px-3 py-1 bg-slate-800 rounded-full border border-slate-700">
                  ~{synapseTokens.toLocaleString()} tokens
                </span>
              </div>
              <p className="text-xs font-sans text-slate-300 mb-4">
                Tree-sitter AST symbol graphs + SQLite WAL CTE recursive traversal + tiktoken context budget enforcement.
              </p>
              <div className="grid grid-cols-3 gap-2 text-xs font-mono text-slate-300 pt-3 border-t border-slate-800">
                <div>Est. Cost: <strong className="text-emerald-400">${synapseMonthlyCost}/mo</strong></div>
                <div>Retrieval: <strong className="text-emerald-400">4.8ms</strong></div>
                <div>Structural Accuracy: <strong className="text-emerald-400">100%</strong></div>
              </div>
            </div>

          </div>

        </div>

      </div>
    </section>
  )
}
