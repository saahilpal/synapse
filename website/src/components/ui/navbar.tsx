"use client"

import React, { useState } from "react"
import Link from "next/link"
import { Cpu, Terminal, Menu, X } from "lucide-react"

export function Navbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-xl">
      <div className="flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8 mx-auto">

        {/* Brand Logo */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="h-9 w-9 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center shadow-lg shadow-blue-500/10 group-hover:border-blue-500/60 transition-all">
            <Cpu className="h-5 w-5 text-blue-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="flex flex-col">
            <span className="font-display font-bold text-lg tracking-tight text-slate-100 group-hover:text-blue-400 transition-colors">
              Synap
            </span>
            <span className="text-[10px] font-mono text-slate-500 -mt-1">Git-Aware Context Engine</span>
          </div>
        </Link>

        {/* Desktop Navigation Links */}
        <nav className="hidden md:flex items-center gap-8 text-xs font-mono tracking-wide text-slate-400">
          <Link href="#architecture" className="hover:text-blue-400 transition-colors">Architecture</Link>
          <Link href="#layers" className="hover:text-cyan-400 transition-colors">3-Layer Model</Link>
          <Link href="#mcp" className="hover:text-emerald-400 transition-colors">MCP Protocol</Link>
          <Link href="#budgeting" className="hover:text-blue-400 transition-colors">Token Calculator</Link>
          <Link href="#cli" className="hover:text-purple-400 transition-colors">CLI Subcommands</Link>
          <Link href="/docs" className="hover:text-slate-100 transition-colors">Docs</Link>
        </nav>

        {/* Right CTA / GitHub Star Link */}
        <div className="hidden md:flex items-center gap-3">
          <a
            href="https://github.com/saahilpal/synapse"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded-xl px-3.5 py-2 text-xs font-mono transition-all hover:border-slate-700"
          >
            <svg className="w-4 h-4 text-slate-400 fill-current" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            <span>GitHub</span>
          </a>

          <a
            href="#cli"
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl px-4 py-2 text-xs font-mono font-medium shadow-lg shadow-blue-600/20 transition-all hover:shadow-blue-500/30"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>pip install synap-git</span>
          </a>
        </div>

        {/* Mobile Menu Toggle */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden text-slate-400 hover:text-slate-100 p-2"
        >
          {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>

      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-slate-950 border-b border-slate-800 px-6 py-4 space-y-3 font-mono text-sm text-slate-300">
          <Link href="#architecture" onClick={() => setMobileMenuOpen(false)} className="block py-1">Architecture</Link>
          <Link href="#layers" onClick={() => setMobileMenuOpen(false)} className="block py-1">3-Layer Model</Link>
          <Link href="#mcp" onClick={() => setMobileMenuOpen(false)} className="block py-1">MCP Protocol</Link>
          <Link href="#budgeting" onClick={() => setMobileMenuOpen(false)} className="block py-1">Token Calculator</Link>
          <Link href="#cli" onClick={() => setMobileMenuOpen(false)} className="block py-1">CLI Subcommands</Link>
          <Link href="/docs" onClick={() => setMobileMenuOpen(false)} className="block py-1">Docs</Link>
          <div className="pt-3 border-t border-slate-800 flex flex-col gap-2">
            <a
              href="https://github.com/saahilpal/synapse"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 bg-slate-900 text-slate-300 py-2 rounded-xl text-xs"
            >
              <svg className="w-4 h-4 text-slate-400 fill-current" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg> GitHub Repository
            </a>
          </div>
        </div>
      )}
    </header>
  )
}
