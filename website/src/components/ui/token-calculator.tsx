"use client"

import React, { useState } from "react"
import { motion } from "framer-motion"
import {
  Zap,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  Sliders,
  DollarSign,
  Clock,
  Sparkles
} from "lucide-react"

export function TokenCalculator() {
  const [locK, setLocK] = useState<number>(75)
  const [queriesPerDay, setQueriesPerDay] = useState<number>(50)

  const rawTokens = Math.round(locK * 1000 * 0.8)
  const synapseTokens = Math.round(Math.min(1400, Math.max(300, locK * 18)))

  const costPerM = 3.0 // Average Claude 3.7 / GPT-4o input cost per 1M tokens
  const rawMonthlyCost = Math.round((rawTokens / 1_000_000) * costPerM * queriesPerDay * 22)
  const synapseMonthlyCost = Math.round((synapseTokens / 1_000_000) * costPerM * queriesPerDay * 22)
  const monthlySavings = Math.max(0, rawMonthlyCost - synapseMonthlyCost)

  const tokenReductionPercent = Math.round(((rawTokens - synapseTokens) / rawTokens) * 100)
  const hoursSaved = Math.round(((7.2 - 0.0092) * queriesPerDay * 22) / 3600)

  return (
    <section id="budgeting" className="py-20 bg-[#090A0F] border-b border-border-subtle relative">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-xs font-mono text-text-secondary mb-3">
            <DollarSign className="w-3.5 h-3.5 text-accent-emerald" />
            <span>Token Budgeting Economics</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-display font-bold text-text-primary tracking-tight">
            Stop Burning Dollars on Context Bloat.
          </h2>
          <p className="mt-4 text-text-secondary text-sm sm:text-base font-sans leading-relaxed">
            Raw file dumps and unranked vector search saturate model context windows with noise. Calculate how much your engineering team saves with Synapse.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center max-w-5xl mx-auto">

          {/* Sliders Control Panel */}
          <div className="lg:col-span-5 minimal-card p-6 sm:p-7 space-y-6 font-mono text-xs">
            <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
              <Sliders className="w-4 h-4 text-accent-blue" />
              Repository Parameters
            </h3>

            {/* Codebase Size */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-text-muted">Repository Lines of Code:</span>
                <span className="text-accent-blue font-bold text-sm">{locK.toLocaleString()}k LOC</span>
              </div>
              <input
                type="range"
                min="10"
                max="500"
                step="5"
                value={locK}
                onChange={(e) => setLocK(Number(e.target.value))}
                className="w-full h-1.5 bg-surface-hover rounded-lg appearance-none cursor-pointer accent-accent-blue"
              />
              <div className="flex justify-between text-[10px] text-text-muted mt-1">
                <span>10k (Small)</span>
                <span>250k</span>
                <span>500k+ (Monorepo)</span>
              </div>
            </div>

            {/* Daily Queries */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-text-muted">Daily AI Agent Invocations:</span>
                <span className="text-accent-emerald font-bold text-sm">{queriesPerDay} prompts / day</span>
              </div>
              <input
                type="range"
                min="5"
                max="200"
                step="5"
                value={queriesPerDay}
                onChange={(e) => setQueriesPerDay(Number(e.target.value))}
                className="w-full h-1.5 bg-surface-hover rounded-lg appearance-none cursor-pointer accent-accent-emerald"
              />
              <div className="flex justify-between text-[10px] text-text-muted mt-1">
                <span>5 (Solo)</span>
                <span>50</span>
                <span>200+ (Team)</span>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-surface-subtle border border-border text-[11px] text-text-secondary font-sans leading-relaxed">
              Based on standard Claude 3.7 / GPT-4o input pricing ($3.00 / 1M tokens) across 22 engineering workdays.
            </div>
          </div>

          {/* Calculated Output Cards */}
          <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono text-xs">

            {/* Monthly Cost Savings */}
            <div className="p-6 rounded-xl bg-accent-emerald/5 border border-accent-emerald/30 flex flex-col justify-between">
              <div>
                <span className="text-[11px] uppercase tracking-wider text-accent-emerald font-bold">
                  Monthly Token Savings
                </span>
                <div className="text-3xl sm:text-4xl font-bold text-accent-emerald mt-3">
                  ${monthlySavings.toLocaleString()}
                </div>
                <span className="text-[11px] text-text-muted mt-1 block">
                  reduced from ${rawMonthlyCost.toLocaleString()}/mo to ${synapseMonthlyCost.toLocaleString()}/mo
                </span>
              </div>
              <div className="mt-4 pt-3 border-t border-accent-emerald/20 text-accent-emerald text-[11px] flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{tokenReductionPercent}% context reduction</span>
              </div>
            </div>

            {/* Engineering Time Saved */}
            <div className="p-6 rounded-xl bg-surface border border-border flex flex-col justify-between">
              <div>
                <span className="text-[11px] uppercase tracking-wider text-text-muted font-bold">
                  Latency Speedup
                </span>
                <div className="text-3xl sm:text-4xl font-bold text-text-primary mt-3">
                  780x
                </div>
                <span className="text-[11px] text-text-muted mt-1 block">
                  Instant 9.2ms response vs 7.2s blocking scans
                </span>
              </div>
              <div className="mt-4 pt-3 border-t border-border text-text-secondary text-[11px] flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-accent-blue" />
                <span>~{hoursSaved} hrs engineer wait time eliminated</span>
              </div>
            </div>

            {/* Tokens per Query Breakdown */}
            <div className="sm:col-span-2 p-5 rounded-xl bg-surface border border-border">
              <div className="flex justify-between items-center mb-3">
                <span className="text-text-muted">Per-Query Token Footprint:</span>
                <span className="text-accent-emerald font-bold">{synapseTokens.toLocaleString()} tokens (Synapse)</span>
              </div>
              <div className="w-full h-3 bg-surface-hover rounded-full overflow-hidden border border-border flex">
                <div
                  style={{ width: `${100 - tokenReductionPercent}%` }}
                  className="bg-accent-emerald h-full rounded-l-full"
                ></div>
                <div
                  style={{ width: `${tokenReductionPercent}%` }}
                  className="bg-[#ef4444]/40 h-full rounded-r-full"
                ></div>
              </div>
              <div className="flex justify-between text-[10px] text-text-muted mt-2">
                <span className="text-accent-emerald">Synapse: {synapseTokens.toLocaleString()} tok</span>
                <span className="text-[#ef4444]">Raw File Dump: {rawTokens.toLocaleString()} tok</span>
              </div>
            </div>

          </div>

        </div>

      </div>
    </section>
  )
}
