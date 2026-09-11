'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Cpu, ArrowLeft, BookOpen, Layers, Terminal, Settings, Zap, Brain, FileText, Users, AlertTriangle, Monitor } from 'lucide-react';

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
    </svg>
  );
}

const NAV_GROUPS = [
  {
    label: 'Getting Started',
    items: [
      { title: 'Introduction', href: '/docs', icon: BookOpen },
      { title: 'Architecture & Design', href: '/docs/architecture', icon: Layers },
    ],
  },
  {
    label: 'Core Systems',
    items: [
      { title: 'Indexing Engine', href: '/docs/indexing', icon: Zap },
      { title: 'L2 Wiki Engine', href: '/docs/wiki', icon: FileText },
      { title: 'L3 Memory System', href: '/docs/memory', icon: Brain },
    ],
  },
  {
    label: 'Integration',
    items: [
      { title: 'CLI Reference', href: '/docs/cli', icon: Terminal },
      { title: 'MCP Setup', href: '/docs/mcp', icon: Zap },
      { title: 'Web Dashboard', href: '/docs/web-ui', icon: Monitor },
      { title: 'LLM Providers', href: '/docs/providers', icon: Settings },
      { title: 'Configuration', href: '/docs/configuration', icon: Settings },
    ],
  },
  {
    label: 'Reference',
    items: [
      { title: 'Troubleshooting', href: '/docs/troubleshooting', icon: AlertTriangle },
      { title: 'Contributing', href: '/docs/contributing', icon: Users },
    ],
  },
];

function SidebarNav() {
  const pathname = usePathname();

  return (
    <aside className="w-full md:w-72 border-r border-[#1e2333] bg-[#0b0d14] flex-shrink-0 flex flex-col sticky top-0 md:h-screen overflow-y-auto">
      {/* Top Brand */}
      <div className="px-6 py-5 border-b border-[#1e2333] flex items-center justify-between flex-shrink-0">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="h-7 w-7 rounded-lg bg-[#0f1118] border border-[#1e2333] flex items-center justify-center group-hover:border-[#38bdf8]/40 transition-colors">
            <Cpu className="h-3.5 w-3.5 text-[#38bdf8]" />
          </div>
          <span className="font-bold text-sm text-[#f8fafc] group-hover:text-white transition-colors tracking-tight">
            Synapse
          </span>
        </Link>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#0f1118] border border-[#1e2333] text-[#64748b]">
          v2.4.0
        </span>
      </div>

      {/* Back to Home */}
      <div className="px-6 pt-5 pb-3 flex-shrink-0">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[#64748b] hover:text-[#94a3b8] transition-colors"
        >
          <ArrowLeft className="w-3 h-3" />
          Back to home
        </Link>
      </div>

      {/* Navigation Groups */}
      <nav className="flex-1 overflow-y-auto px-4 pb-8 space-y-6">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="px-2 mb-2 text-[10px] font-bold uppercase tracking-widest text-[#475569]">
              {group.label}
            </div>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-mono transition-all ${
                        isActive
                          ? 'bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/20 font-semibold'
                          : 'text-[#64748b] hover:text-[#94a3b8] hover:bg-[#0f1118]'
                      }`}
                    >
                      <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-[#38bdf8]' : 'text-[#475569]'}`} />
                      {item.title}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer links */}
      <div className="px-6 py-4 border-t border-[#1e2333] flex-shrink-0 space-y-2">
        <a
          href="https://github.com/saahilpal/synapse"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 text-[11px] font-mono text-[#475569] hover:text-[#94a3b8] transition-colors"
        >
          <GithubIcon className="w-3.5 h-3.5" />
          GitHub — saahilpal/synapse
        </a>
        <a
          href="https://pypi.org/project/synap-git/"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 text-[11px] font-mono text-[#475569] hover:text-[#94a3b8] transition-colors"
        >
          <span className="text-[10px] font-bold">PyPI</span>
          synap-git
        </a>
      </div>
    </aside>
  );
}

export default function DocsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[#090a0f] flex flex-col md:flex-row">
      <SidebarNav />

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-12 md:px-10 md:py-14 lg:px-16 lg:py-16">
          <article className="
            prose prose-sm max-w-none

            /* Base text */
            prose-p:text-[#94a3b8] prose-p:leading-7 prose-p:font-sans

            /* Headings */
            prose-headings:font-display prose-headings:text-[#f8fafc] prose-headings:tracking-tight
            prose-h1:text-3xl prose-h1:font-bold prose-h1:mb-3 prose-h1:border-b prose-h1:border-[#1e2333] prose-h1:pb-4
            prose-h2:text-xl prose-h2:font-semibold prose-h2:mt-10 prose-h2:mb-4 prose-h2:text-[#e2e8f0]
            prose-h3:text-base prose-h3:font-semibold prose-h3:mt-6 prose-h3:mb-2 prose-h3:text-[#cbd5e1]

            /* Links */
            prose-a:text-[#38bdf8] hover:prose-a:text-[#7dd3fc] prose-a:no-underline hover:prose-a:underline prose-a:font-medium

            /* Inline code */
            prose-code:text-[#38bdf8] prose-code:bg-[#0f1118] prose-code:border prose-code:border-[#1e2333]
            prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-[11px] prose-code:font-mono
            prose-code:before:content-none prose-code:after:content-none

            /* Code blocks */
            prose-pre:bg-[#08090d] prose-pre:border prose-pre:border-[#1e2333] prose-pre:rounded-xl
            prose-pre:p-4 prose-pre:overflow-x-auto prose-pre:text-[12px]
            prose-pre:font-mono prose-pre:text-[#94a3b8]

            /* Lists */
            prose-ul:text-[#94a3b8] prose-ul:space-y-1 prose-li:leading-6
            prose-ol:text-[#94a3b8]

            /* Strong */
            prose-strong:text-[#e2e8f0] prose-strong:font-semibold

            /* HR */
            prose-hr:border-[#1e2333] prose-hr:my-8

            /* Tables */
            prose-table:text-xs prose-table:font-mono
            prose-th:text-[#94a3b8] prose-th:bg-[#0f1118] prose-th:border prose-th:border-[#1e2333] prose-th:px-3 prose-th:py-2
            prose-td:border prose-td:border-[#1e2333] prose-td:px-3 prose-td:py-2 prose-td:text-[#64748b]

            /* Blockquotes */
            prose-blockquote:border-l-[#38bdf8] prose-blockquote:text-[#64748b] prose-blockquote:italic prose-blockquote:bg-[#0f1118] prose-blockquote:rounded-r-lg prose-blockquote:py-1
          ">
            {children}
          </article>

          {/* Page Footer */}
          <div className="mt-16 pt-8 border-t border-[#1e2333] flex items-center justify-between text-[11px] font-mono text-[#475569]">
            <span>Synapse Engine — v2.4.0</span>
            <div className="flex items-center gap-4">
              <a href="https://github.com/saahilpal/synapse" target="_blank" rel="noopener noreferrer" className="hover:text-[#94a3b8] transition-colors">GitHub</a>
              <a href="https://pypi.org/project/synap-git/" target="_blank" rel="noopener noreferrer" className="hover:text-[#94a3b8] transition-colors">PyPI</a>
              <Link href="/" className="hover:text-[#94a3b8] transition-colors">← Home</Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
