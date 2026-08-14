"use client"

import React from "react"
import { Navbar } from "@/components/ui/navbar"
import { SynapseHero } from "@/components/ui/synapse-hero"
import { BenchmarkComparison } from "@/components/ui/benchmark-comparison"
import { ArchitectureDiagram } from "@/components/ui/architecture-diagram"
import { ThreeLayerExplorer } from "@/components/ui/three-layer-explorer"
import { McpInspector } from "@/components/ui/mcp-inspector"
import { IdeConfigGenerator } from "@/components/ui/ide-config-generator"
import { CliPlayground } from "@/components/ui/cli-playground"
import { TokenCalculator } from "@/components/ui/token-calculator"
import { FaqAndGuide } from "@/components/ui/faq-and-guide"
import { Footer } from "@/components/ui/footer"

export default function Home() {
  return (
    <div className="relative min-h-screen bg-background text-text-primary font-sans selection:bg-accent-blue/20 selection:text-white overflow-x-hidden antialiased">
      {/* Top Header Navigation */}
      <Navbar />

      <main>
        {/* 1. Hero Section & Live Dual-Engine Sandbox */}
        <SynapseHero />

        {/* 2. 780x Latency Speedup & Engineering Benchmark */}
        <BenchmarkComparison />

        {/* 3. High-Level Architecture & Module Topology */}
        <ArchitectureDiagram />

        {/* 4. 3-Layer Context Model (L1 AST, L2 Wiki, L3 Memory) */}
        <ThreeLayerExplorer />

        {/* 5. FastMCP Stdio Protocol Inspector */}
        <McpInspector />

        {/* 6. 1-Click Agent Integration (Cursor, Claude Code, Windsurf, Roo) */}
        <IdeConfigGenerator />

        {/* 7. Interactive CLI Reference & Terminal Simulator */}
        <CliPlayground />

        {/* 8. Token Calculator & Economic Cost Reduction Model */}
        <TokenCalculator />

        {/* 9. 3-Step Setup Guide & Developer FAQ */}
        <FaqAndGuide />
      </main>

      {/* Footer */}
      <Footer />
    </div>
  )
}
