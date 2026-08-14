"use client"

import React, { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  HelpCircle,
  ChevronDown,
  Terminal,
  ShieldCheck,
  Cpu,
  Lock,
  Zap,
  Layers,
  ArrowRight
} from "lucide-react"

interface FAQItem {
  question: string
  answer: string
  category: "setup" | "security" | "providers" | "performance"
}

const FAQS: FAQItem[] = [
  {
    question: "How does Synapse achieve 9.2ms MCP search latency?",
    answer: "Synapse eliminates synchronous LLM router calls from the hot path. When an agent queries the codebase, Synapse runs deterministic intent classification, queries pre-indexed Tree-sitter AST nodes and caller/callee graphs via SQLite WAL recursive CTEs, and computes cosine similarities with LRU-cached vector dot-products.",
    category: "performance"
  },
  {
    question: "Does my proprietary source code ever leave my machine?",
    answer: "No. Synapse is 100% local-first. All AST symbols, import edges, vector embeddings, and semantic wiki files are stored in your local '.synap/synap.db' SQLite database. When configured with local Ollama, zero network packets leave your workstation.",
    category: "security"
  },
  {
    question: "Which LLM and embedding providers are supported?",
    answer: "Synapse supports Ollama (recommended: qwen2.5-coder:14b & nomic-embed-text for 100% free offline use), Anthropic Claude, OpenAI, Google Gemini, and OpenRouter. You can configure providers interactively with `synap setup`.",
    category: "providers"
  },
  {
    question: "How does Synapse handle Git branches, merges, and commit shifts?",
    answer: "Synapse fingerprints the filesystem modification times of `.git/HEAD`, `.git/index`, and `.git/refs` in under 0.001ms. When a commit shift or branch switch occurs, only the modified file deltas are re-parsed by Tree-sitter and updated in SQLite.",
    category: "performance"
  },
  {
    question: "How do I configure Synapse in Cursor, Claude Code, or Windsurf?",
    answer: "Run `synap mcp config` in your terminal or use our 1-click IDE Config Generator above. Add the generated JSON snippet to your `.cursor/mcp.json` or run `claude mcp add synapse synap -- mcp serve .` in Claude Code.",
    category: "setup"
  },
  {
    question: "What languages does Tree-sitter parse in Synapse?",
    answer: "Synapse natively parses Python, TypeScript, TSX, JavaScript, JSX, Rust, Go, C, C++, C#, Java, Kotlin, Swift, Scala, Ruby, PHP, SQL, Markdown, JSON, TOML, and YAML.",
    category: "setup"
  }
]

export function FaqAndGuide() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  const toggleFAQ = (index: number) => {
    setOpenIndex(openIndex === index ? null : index)
  }

  return (
    <section className="py-20 bg-surface-subtle/30 border-b border-border-subtle">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="max-w-3xl mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-text-secondary text-xs font-mono mb-4">
            <HelpCircle className="w-3.5 h-3.5 text-accent-blue" />
            <span>Developer Guide & Frequently Asked Questions</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary tracking-tight">
            Engineered for Precision & Transparency.
          </h2>
          <p className="mt-3 text-text-secondary font-sans text-sm sm:text-base leading-relaxed">
            Everything you need to know about setting up, integrating, and deploying Synapse across your developer toolchain.
          </p>
        </div>

        {/* 3-Step Quickstart Guide */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16 font-mono text-xs">

          <div className="minimal-card p-6 flex flex-col justify-between">
            <div>
              <span className="text-xs font-bold text-accent-blue uppercase tracking-wider block mb-3">
                Step 01
              </span>
              <h3 className="font-bold text-text-primary text-base font-display">Install Package</h3>
              <p className="mt-2 text-text-secondary font-sans leading-relaxed">
                Install Synapse globally via pip or uv tool with zero heavy build dependencies.
              </p>
            </div>
            <div className="mt-4 p-3 rounded-lg bg-[#08090D] border border-border text-text-primary">
              <code>pip install synap-git</code>
            </div>
          </div>

          <div className="minimal-card p-6 flex flex-col justify-between">
            <div>
              <span className="text-xs font-bold text-accent-emerald uppercase tracking-wider block mb-3">
                Step 02
              </span>
              <h3 className="font-bold text-text-primary text-base font-display">Initialize Repo</h3>
              <p className="mt-2 text-text-secondary font-sans leading-relaxed">
                Run init in your repository to build the local SQLite AST graph and semantic wiki.
              </p>
            </div>
            <div className="mt-4 p-3 rounded-lg bg-[#08090D] border border-border text-text-primary">
              <code>synap init .</code>
            </div>
          </div>

          <div className="minimal-card p-6 flex flex-col justify-between">
            <div>
              <span className="text-xs font-bold text-accent-amber uppercase tracking-wider block mb-3">
                Step 03
              </span>
              <h3 className="font-bold text-text-primary text-base font-display">Mount MCP Server</h3>
              <p className="mt-2 text-text-secondary font-sans leading-relaxed">
                Connect Cursor or Claude Code to provide your AI agents with sub-10ms context.
              </p>
            </div>
            <div className="mt-4 p-3 rounded-lg bg-[#08090D] border border-border text-text-primary">
              <code>synap start .</code>
            </div>
          </div>

        </div>

        {/* Accordion FAQ Grid */}
        <div className="max-w-4xl mx-auto space-y-3 font-mono text-xs">
          {FAQS.map((faq, index) => {
            const isOpen = openIndex === index
            return (
              <div
                key={index}
                className={`minimal-card overflow-hidden transition-all ${isOpen ? "border-accent-blue/40 bg-surface" : "bg-surface/50"}`}
              >
                <button
                  onClick={() => toggleFAQ(index)}
                  className="w-full text-left p-5 flex items-center justify-between cursor-pointer"
                >
                  <span className="font-semibold text-text-primary text-sm font-sans">
                    {faq.question}
                  </span>
                  <ChevronDown
                    className={`w-4 h-4 text-text-muted transition-transform shrink-0 ml-4 ${
                      isOpen ? "rotate-180 text-accent-blue" : ""
                    }`}
                  />
                </button>

                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-5 pb-5 text-text-secondary font-sans text-xs sm:text-sm leading-relaxed border-t border-border/50 pt-3">
                        {faq.answer}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>

      </div>
    </section>
  )
}
