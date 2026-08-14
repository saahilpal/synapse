"use client"

import React from "react"
import { Navbar } from "@/components/ui/navbar"
import { SynapseHero } from "@/components/ui/synapse-hero"
import { ArchitectureDiagram } from "@/components/ui/architecture-diagram"
import { ThreeLayerExplorer } from "@/components/ui/three-layer-explorer"
import { McpInspector } from "@/components/ui/mcp-inspector"
import { TokenCalculator } from "@/components/ui/token-calculator"
import { CliPlayground } from "@/components/ui/cli-playground"
import { Footer } from "@/components/ui/footer"

export default function Home() {
  return (
    <div className="relative min-h-screen bg-background text-text-primary font-sans selection:bg-accent-blue/30 selection:text-text-primary overflow-x-hidden antialiased">
      {/* Top Header Navigation */}
      <Navbar />

      <main>
        {/* Hero Section */}
        <SynapseHero />

        {/* HLD Architecture Visualizer */}
        <ArchitectureDiagram />

        {/* 3-Layer Context Model Explorer (L1, L2, L3) */}
        <ThreeLayerExplorer />

        {/* FastMCP Stdio Protocol Inspector */}
        <McpInspector />

        {/* Token Calculator & Savings Economics */}
        <TokenCalculator />

        {/* CLI Terminal Playground */}
        <CliPlayground />
      </main>

      {/* Footer */}
      <Footer />
    </div>
  )
}
