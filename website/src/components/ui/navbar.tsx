"use client"

import React, { useState } from "react"
import Link from "next/link"
import { Cpu, Terminal, Menu, X, Copy, Check, ExternalLink } from "lucide-react"

export function Navbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const copyInstall = () => {
    navigator.clipboard.writeText("pip install synap-git")
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border-subtle bg-[#090A0F]/85 backdrop-blur-md">
      <div className="flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8 mx-auto">

        {/* Brand Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <div className="h-8 w-8 rounded-lg bg-surface border border-border flex items-center justify-center group-hover:border-accent-blue/40 transition-colors">
            <Cpu className="h-4 w-4 text-accent-blue group-hover:scale-105 transition-transform" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-display font-bold text-base tracking-tight text-text-primary group-hover:text-white transition-colors">
              Synapse
            </span>
            <span className="text-[10px] font-mono font-medium px-1.5 py-0.5 rounded bg-surface border border-border text-text-muted">
              v2.4.0
            </span>
          </div>
        </Link>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center gap-7 text-xs font-mono tracking-wider text-text-secondary">
          <Link href="#architecture" className="hover:text-text-primary transition-colors">Architecture</Link>
          <Link href="#benchmark" className="hover:text-accent-emerald transition-colors">780x Benchmark</Link>
          <Link href="#layers" className="hover:text-text-primary transition-colors">3-Layer Model</Link>
          <Link href="#mcp" className="hover:text-text-primary transition-colors">MCP Protocol</Link>
          <Link href="#ide-setup" className="hover:text-text-primary transition-colors">IDE Setup</Link>
          <Link href="#cli" className="hover:text-text-primary transition-colors">CLI Reference</Link>
          <Link href="/docs" className="text-accent-blue hover:text-white transition-colors flex items-center gap-1">
            Docs <ExternalLink className="w-3 h-3" />
          </Link>
        </nav>

        {/* Right Actions */}
        <div className="hidden md:flex items-center gap-3">
          <a
            href="https://github.com/saahilpal/synapse"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 bg-surface hover:bg-surface-hover text-text-secondary hover:text-text-primary border border-border rounded-lg px-3 py-1.5 text-xs font-mono transition-all"
          >
            <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            <span>GitHub</span>
          </a>

          <button
            onClick={copyInstall}
            className="flex items-center gap-2 bg-text-primary hover:bg-white text-background rounded-lg px-3.5 py-1.5 text-xs font-mono font-medium transition-all shadow-sm cursor-pointer"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>pip install synap-git</span>
            {copied ? <Check className="w-3.5 h-3.5 text-accent-emerald" /> : <Copy className="w-3.5 h-3.5 opacity-60" />}
          </button>
        </div>

        {/* Mobile Toggle */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden text-text-secondary hover:text-text-primary p-2"
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-surface border-b border-border px-6 py-5 space-y-3 font-mono text-xs text-text-secondary">
          <Link href="#architecture" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 hover:text-text-primary">Architecture</Link>
          <Link href="#benchmark" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 hover:text-text-primary">780x Benchmark</Link>
          <Link href="#layers" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 hover:text-text-primary">3-Layer Model</Link>
          <Link href="#mcp" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 hover:text-text-primary">MCP Protocol</Link>
          <Link href="#ide-setup" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 hover:text-text-primary">IDE Setup</Link>
          <Link href="#cli" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 hover:text-text-primary">CLI Reference</Link>
          <Link href="/docs" onClick={() => setMobileMenuOpen(false)} className="block py-1.5 text-accent-blue">Documentation</Link>
          <div className="pt-3 border-t border-border flex flex-col gap-2">
            <button
              onClick={copyInstall}
              className="flex items-center justify-center gap-2 bg-text-primary text-background py-2 rounded-lg text-xs font-medium"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>pip install synap-git</span>
              {copied && <Check className="w-3.5 h-3.5 text-emerald-600" />}
            </button>
          </div>
        </div>
      )}
    </header>
  )
}
