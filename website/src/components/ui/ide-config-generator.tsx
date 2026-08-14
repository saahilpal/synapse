"use client"

import React, { useState } from "react"
import { motion } from "framer-motion"
import { Terminal, Copy, Check, Sparkles, Code2, Cpu, ArrowRight, Laptop } from "lucide-react"

interface IDEConfig {
  id: string
  name: string
  fileTarget: string
  snippet: string
  instructions: string
  command?: string
}

const IDE_CONFIGS: IDEConfig[] = [
  {
    id: "cursor",
    name: "Cursor",
    fileTarget: ".cursor/mcp.json",
    instructions: "Add to your project's .cursor/mcp.json or global Cursor MCP Settings:",
    snippet: `{
  "mcpServers": {
    "synapse": {
      "command": "synap",
      "args": ["mcp", "serve", "\${workspaceFolder}"]
    }
  }
}`
  },
  {
    id: "claudecode",
    name: "Claude Code",
    fileTarget: "Terminal Command",
    instructions: "Run this command in your repository to mount the Synapse MCP server in Claude Code:",
    snippet: `claude mcp add synapse synap -- mcp serve .`,
    command: `claude mcp add synapse synap -- mcp serve .`
  },
  {
    id: "windsurf",
    name: "Windsurf",
    fileTarget: "~/.codeium/windsurf/mcp_config.json",
    instructions: "Add to your Windsurf Cascade MCP Configuration file:",
    snippet: `{
  "mcpServers": {
    "synapse": {
      "command": "synap",
      "args": ["mcp", "serve", "."]
    }
  }
}`
  },
  {
    id: "roocode",
    name: "Roo Code / Cline",
    fileTarget: "roo_code_mcp_settings.json",
    instructions: "Add to your Roo Code or Cline MCP servers configuration:",
    snippet: `{
  "mcpServers": {
    "synapse": {
      "command": "synap",
      "args": ["mcp", "serve", "."]
    }
  }
}`
  },
  {
    id: "cursorrules",
    name: ".cursorrules",
    fileTarget: ".cursorrules",
    instructions: "Add this rule block to ensure your agent consults Synapse before editing code:",
    snippet: `# Synapse Context Engine Guidelines
Before refactoring or creating files:
1. Call 'search' tool to inspect exact AST symbol definitions and caller/callee graphs.
2. Review '.synap/wiki/overview.md' for module architectural constraints.
3. Record key technical decisions using 'log_decision'.`
  }
]

export function IdeConfigGenerator() {
  const [selectedIde, setSelectedIde] = useState<IDEConfig>(IDE_CONFIGS[0])
  const [copied, setCopied] = useState(false)

  const copyConfig = () => {
    navigator.clipboard.writeText(selectedIde.snippet)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section id="ide-setup" className="py-20 border-b border-border-subtle bg-[#090A0F]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        {/* Section Header */}
        <div className="max-w-3xl mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-text-secondary text-xs font-mono mb-4">
            <Laptop className="w-3.5 h-3.5 text-accent-blue" />
            <span>1-Click Agent Integration</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary tracking-tight">
            Connect to Any AI Coding Agent.
          </h2>
          <p className="mt-3 text-text-secondary font-sans text-sm sm:text-base leading-relaxed">
            Synapse speaks standard FastMCP over stdio. Copy and paste the configuration block for your editor to give your agent instant 9.2ms codebase awareness.
          </p>
        </div>

        {/* IDE Selector Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

          {/* Left: IDE Tabs */}
          <div className="lg:col-span-4 space-y-2 font-mono text-xs">
            {IDE_CONFIGS.map(ide => (
              <button
                key={ide.id}
                onClick={() => setSelectedIde(ide)}
                className={`w-full text-left p-3.5 rounded-xl border transition-all flex items-center justify-between cursor-pointer ${
                  selectedIde.id === ide.id
                    ? "bg-surface-hover border-accent-blue/50 text-text-primary font-medium shadow-md"
                    : "bg-surface/50 border-border text-text-secondary hover:border-border-strong hover:bg-surface"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className={`h-6 w-6 rounded-md flex items-center justify-center text-[10px] font-bold ${
                    selectedIde.id === ide.id ? "bg-accent-blue/20 text-accent-blue" : "bg-surface text-text-muted"
                  }`}>
                    {ide.name.substring(0, 2).toUpperCase()}
                  </div>
                  <span>{ide.name}</span>
                </div>
                <span className="text-[11px] text-text-muted">{ide.fileTarget.split("/").pop()}</span>
              </button>
            ))}
          </div>

          {/* Right: Config Box */}
          <div className="lg:col-span-8 minimal-card p-6 font-mono text-xs">
            <div className="flex items-center justify-between pb-4 border-b border-border">
              <div>
                <span className="font-bold text-text-primary text-sm">{selectedIde.name} Configuration</span>
                <span className="text-[11px] text-text-muted block mt-0.5">{selectedIde.fileTarget}</span>
              </div>

              <button
                onClick={copyConfig}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface border border-border text-text-secondary hover:text-text-primary hover:border-border-strong transition-all cursor-pointer"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-accent-emerald" />
                    <span className="text-accent-emerald">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Config</span>
                  </>
                )}
              </button>
            </div>

            <p className="mt-4 text-text-secondary font-sans text-xs">
              {selectedIde.instructions}
            </p>

            <pre className="mt-3 p-4 rounded-xl bg-[#08090D] border border-border text-text-primary overflow-x-auto text-[11px] leading-relaxed">
              {selectedIde.snippet}
            </pre>

            <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-text-muted text-[11px]">
              <span>Protocol: FastMCP Stdio (Standard I/O)</span>
              <span className="text-accent-emerald flex items-center gap-1">
                Zero Port Collisions
              </span>
            </div>
          </div>

        </div>

      </div>
    </section>
  )
}
