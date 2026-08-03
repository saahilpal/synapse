"use client"

import React from "react"
import Link from "next/link"
import { Cpu, ArrowUpRight, ShieldCheck } from "lucide-react"

export function Footer() {
  return (
    <footer className="bg-slate-950 border-t border-slate-800/80 text-slate-400 font-mono text-xs py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 pb-12 border-b border-slate-900">

          {/* Brand Col */}
          <div className="md:col-span-2 space-y-3">
            <div className="flex items-center gap-2.5">
              <div className="h-7 w-7 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
                <Cpu className="h-4 w-4 text-blue-400" />
              </div>
              <span className="font-display font-bold text-base text-slate-100">Synapse Engine</span>
            </div>
            <p className="font-sans text-xs text-slate-400 max-w-md leading-relaxed">
              Deterministic Git-aware structural retrieval engine for AI coding agents. Projects repository HEAD commits into SQLite AST graphs, serving precision token-budgeted context via stdio MCP.
            </p>
            <div className="text-[11px] text-emerald-400 flex items-center gap-1.5 pt-1">
              <ShieldCheck className="w-3.5 h-3.5" /> 100% Open Source (Apache / MIT Licensed)
            </div>
          </div>

          {/* Core Modules Links */}
          <div className="space-y-2">
            <div className="text-slate-200 font-bold uppercase tracking-wider text-[11px]">Architecture</div>
            <ul className="space-y-1.5 text-slate-400">
              <li><Link href="#architecture" className="hover:text-blue-400 transition-colors">Tree-sitter AST Parser</Link></li>
              <li><Link href="#architecture" className="hover:text-blue-400 transition-colors">SQLite WAL Engine</Link></li>
              <li><Link href="#layers" className="hover:text-blue-400 transition-colors">L1 Structural Symbol Graph</Link></li>
              <li><Link href="#layers" className="hover:text-blue-400 transition-colors">L2 Asynchronous Wiki</Link></li>
              <li><Link href="#layers" className="hover:text-blue-400 transition-colors">L3 Behavioral Memory</Link></li>
            </ul>
          </div>

          {/* MCP & Tooling Links */}
          <div className="space-y-2">
            <div className="text-slate-200 font-bold uppercase tracking-wider text-[11px]">Protocols & CLI</div>
            <ul className="space-y-1.5 text-slate-400">
              <li><Link href="#mcp" className="hover:text-emerald-400 transition-colors">FastMCP Stdio Server</Link></li>
              <li><Link href="#cli" className="hover:text-purple-400 transition-colors">synap setup & doctor</Link></li>
              <li><Link href="#budgeting" className="hover:text-cyan-400 transition-colors">tiktoken Context Budgeter</Link></li>
              <li><a href="https://pypi.org/project/synap-git/" target="_blank" rel="noopener noreferrer" className="hover:text-slate-100 flex items-center gap-1">PyPI Package <ArrowUpRight className="w-3 h-3" /></a></li>
              <li><a href="https://github.com/saahilpal/synapse" target="_blank" rel="noopener noreferrer" className="hover:text-slate-100 flex items-center gap-1">GitHub Repo <ArrowUpRight className="w-3 h-3" /></a></li>
            </ul>
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-slate-500 text-[11px]">
          <div>
            © {new Date().getFullYear()} Synapse AI. Built for deterministic agent context.
          </div>
          <div className="flex items-center gap-4">
            <span>Python 3.12+</span>
            <span>•</span>
            <span>SQLite WAL</span>
            <span>•</span>
            <span>Model Context Protocol</span>
          </div>
        </div>

      </div>
    </footer>
  )
}
