"use client"

import React from "react"
import Link from "next/link"
import { Cpu, ArrowUpRight, ShieldCheck, Terminal, Heart } from "lucide-react"

export function Footer() {
  return (
    <footer className="bg-[#07080B] border-t border-border-subtle text-text-secondary font-mono text-xs py-14">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 pb-12 border-b border-border">

          {/* Brand Column */}
          <div className="md:col-span-2 space-y-3.5">
            <div className="flex items-center gap-2.5">
              <div className="h-7 w-7 rounded-lg bg-surface border border-border flex items-center justify-center">
                <Cpu className="h-4 w-4 text-accent-blue" />
              </div>
              <span className="font-display font-bold text-base text-text-primary">Synapse Engine</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border text-text-muted">
                v2.4.0
              </span>
            </div>
            <p className="font-sans text-xs text-text-secondary max-w-md leading-relaxed">
              Deterministic Git-aware structural retrieval engine for AI coding agents. Projects repository commits into SQLite AST graphs, serving precision token-budgeted context via stdio FastMCP in 9.2ms.
            </p>
            <div className="text-[11px] text-accent-emerald flex items-center gap-1.5 pt-1">
              <ShieldCheck className="w-3.5 h-3.5" /> 100% Local-First & Open Source
            </div>
          </div>

          {/* Architecture Links */}
          <div className="space-y-2.5">
            <div className="text-text-primary font-bold uppercase tracking-wider text-[11px]">Architecture</div>
            <ul className="space-y-2 text-text-secondary">
              <li><Link href="#architecture" className="hover:text-text-primary transition-colors">Tree-sitter AST Parser</Link></li>
              <li><Link href="#architecture" className="hover:text-text-primary transition-colors">SQLite WAL Storage</Link></li>
              <li><Link href="#layers" className="hover:text-text-primary transition-colors">L1 Structural Code Graph</Link></li>
              <li><Link href="#layers" className="hover:text-text-primary transition-colors">L2 Asynchronous Wiki</Link></li>
              <li><Link href="#layers" className="hover:text-text-primary transition-colors">L3 Behavioral Memory</Link></li>
            </ul>
          </div>

          {/* Integration Links */}
          <div className="space-y-2.5">
            <div className="text-text-primary font-bold uppercase tracking-wider text-[11px]">Integrations & CLI</div>
            <ul className="space-y-2 text-text-secondary">
              <li><Link href="#mcp" className="hover:text-text-primary transition-colors">FastMCP Stdio Server</Link></li>
              <li><Link href="#ide-setup" className="hover:text-text-primary transition-colors">Cursor & Claude Code Setup</Link></li>
              <li><Link href="#cli" className="hover:text-text-primary transition-colors">CLI Reference</Link></li>
              <li><Link href="/docs" className="hover:text-accent-blue transition-colors">Documentation</Link></li>
              <li><a href="https://pypi.org/project/synap-git/" target="_blank" rel="noopener noreferrer" className="hover:text-text-primary flex items-center gap-1">PyPI (synap-git) <ArrowUpRight className="w-3 h-3" /></a></li>
              <li><a href="https://github.com/saahilpal/synapse" target="_blank" rel="noopener noreferrer" className="hover:text-text-primary flex items-center gap-1">GitHub Repo <ArrowUpRight className="w-3 h-3" /></a></li>
            </ul>
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-text-muted text-[11px]">
          <div>
            © {new Date().getFullYear()} Synapse. Built for deterministic AI context grounding.
          </div>
          <div className="flex items-center gap-3">
            <span>Python 3.12+</span>
            <span>•</span>
            <span>SQLite WAL</span>
            <span>•</span>
            <span>FastMCP Protocol</span>
            <span>•</span>
            <span>Tree-sitter AST</span>
          </div>
        </div>

      </div>
    </footer>
  )
}
