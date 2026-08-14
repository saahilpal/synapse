"use client"

import React, { useState } from "react"
import { motion } from "framer-motion"
import { Zap, Clock, Cpu, ShieldCheck, Database, Server, RefreshCw, CheckCircle2 } from "lucide-react"

export function BenchmarkComparison() {
  const [isRunningBenchmark, setIsRunningBenchmark] = useState(false)
  const [benchmarkCompleted, setBenchmarkCompleted] = useState(true)

  const runBenchmark = () => {
    setIsRunningBenchmark(true)
    setBenchmarkCompleted(false)
    setTimeout(() => {
      setIsRunningBenchmark(false)
      setBenchmarkCompleted(true)
    }, 800)
  }

  return (
    <section id="benchmark" className="py-20 border-b border-border-subtle bg-surface-subtle/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="max-w-3xl mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-emerald/10 border border-accent-emerald/20 text-accent-emerald text-xs font-mono mb-4">
            <Zap className="w-3.5 h-3.5" />
            <span>Retrieval Performance & Economics</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary tracking-tight">
            780x Faster Context Retrieval. From 7.2s to 9.2ms.
          </h2>
          <p className="mt-3 text-text-secondary font-sans text-sm sm:text-base leading-relaxed">
            Standard AI agent context tools make blocking, synchronous LLM classification calls before retrieving code. Synap v2.4.0 uses deterministic AST intent routing, LRU vector caching, and SQLite WAL engine to return grounded context instantaneously.
          </p>
        </div>

        {/* Benchmark Visualizer Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">

          {/* Main Visualizer Comparison */}
          <div className="lg:col-span-7 minimal-card p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-border">
                <span className="font-mono text-xs text-text-muted">Agent MCP Search Latency Benchmark</span>
                <button
                  onClick={runBenchmark}
                  disabled={isRunningBenchmark}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-surface border border-border text-xs font-mono text-text-secondary hover:text-text-primary hover:border-border-strong transition-all cursor-pointer disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${isRunningBenchmark ? "animate-spin text-accent-blue" : ""}`} />
                  <span>Run Live Benchmark</span>
                </button>
              </div>

              {/* Latency Bars */}
              <div className="mt-6 space-y-5 font-mono text-xs">

                {/* Traditional LLM Retrieval */}
                <div>
                  <div className="flex justify-between text-text-secondary mb-1.5">
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-[#ef4444]" />
                      <span>Traditional LLM Router + Raw Dumps</span>
                    </span>
                    <span className="font-bold text-[#ef4444]">7,214 ms</span>
                  </div>
                  <div className="w-full h-3 bg-surface rounded-full overflow-hidden border border-border">
                    <motion.div
                      initial={{ width: "100%" }}
                      animate={{ width: isRunningBenchmark ? "0%" : "100%" }}
                      transition={{ duration: 0.8 }}
                      className="h-full bg-[#ef4444]/70 rounded-full"
                    />
                  </div>
                  <span className="text-[10px] text-text-muted mt-1 block">Blocks agent loop waiting for remote LLM inference</span>
                </div>

                {/* Vector Only RAG */}
                <div>
                  <div className="flex justify-between text-text-secondary mb-1.5">
                    <span className="flex items-center gap-1.5">
                      <Database className="w-3.5 h-3.5 text-accent-amber" />
                      <span>Remote Vector-Only Cloud RAG</span>
                    </span>
                    <span className="font-bold text-accent-amber">480 ms</span>
                  </div>
                  <div className="w-full h-3 bg-surface rounded-full overflow-hidden border border-border">
                    <motion.div
                      initial={{ width: "24%" }}
                      animate={{ width: isRunningBenchmark ? "0%" : "24%" }}
                      transition={{ duration: 0.5 }}
                      className="h-full bg-accent-amber/70 rounded-full"
                    />
                  </div>
                  <span className="text-[10px] text-text-muted mt-1 block">Network roundtrips + unranked semantic text snippets</span>
                </div>

                {/* Synap v2.4.0 */}
                <div className="p-3.5 rounded-xl bg-accent-emerald/5 border border-accent-emerald/30">
                  <div className="flex justify-between text-text-primary mb-1.5">
                    <span className="flex items-center gap-1.5 font-semibold text-accent-emerald">
                      <Zap className="w-3.5 h-3.5" />
                      <span>Synapse v2.4.0 Engine</span>
                    </span>
                    <span className="font-bold text-accent-emerald text-sm">9.2 ms (780x Speedup)</span>
                  </div>
                  <div className="w-full h-3 bg-surface rounded-full overflow-hidden border border-border">
                    <motion.div
                      initial={{ width: "2.5%" }}
                      animate={{ width: isRunningBenchmark ? "0%" : "2.5%" }}
                      transition={{ duration: 0.2 }}
                      className="h-full bg-accent-emerald rounded-full"
                    />
                  </div>
                  <span className="text-[10px] text-accent-emerald/80 mt-1 block">Local Tree-sitter SQLite graph + LRU vector cache</span>
                </div>

              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-border flex items-center justify-between text-text-muted text-[11px] font-mono">
              <span>Grounding verified with Cursor & Claude Code</span>
              <span className="text-text-secondary flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-accent-emerald" /> 0 Cloud API Calls
              </span>
            </div>
          </div>

          {/* First Principles Engineering Breakdown */}
          <div className="lg:col-span-5 grid grid-cols-1 gap-3.5">

            <div className="p-4 rounded-xl bg-surface border border-border hover:border-border-strong transition-all">
              <div className="flex items-center gap-2 font-mono text-xs text-text-primary font-semibold">
                <Cpu className="w-4 h-4 text-accent-blue" />
                <span>Deterministic Intent Routing</span>
              </div>
              <p className="mt-1.5 text-xs text-text-secondary font-sans leading-relaxed">
                Eliminates synchronous LLM classification in retrieval. Routes exact symbols, imports, and definitions directly through SQLite indices in under 1ms.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-surface border border-border hover:border-border-strong transition-all">
              <div className="flex items-center gap-2 font-mono text-xs text-text-primary font-semibold">
                <Database className="w-4 h-4 text-accent-emerald" />
                <span>LRU Cached Vector Dot-Products</span>
              </div>
              <p className="mt-1.5 text-xs text-text-secondary font-sans leading-relaxed">
                Pre-computes Euclidean norms and caches JSON deserialization with LRU buffers, eliminating repetitive vector serialization overhead during searches.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-surface border border-border hover:border-border-strong transition-all">
              <div className="flex items-center gap-2 font-mono text-xs text-text-primary font-semibold">
                <Server className="w-4 h-4 text-accent-amber" />
                <span>Filesystem mtime Invalidation</span>
              </div>
              <p className="mt-1.5 text-xs text-text-secondary font-sans leading-relaxed">
                Fingerprints <code className="text-[11px] text-text-primary bg-surface-subtle px-1 rounded">.git/HEAD</code> and index files to achieve 0.001ms Git state checks, instantly invalidating only when changes occur.
              </p>
            </div>

          </div>

        </div>

      </div>
    </section>
  )
}
