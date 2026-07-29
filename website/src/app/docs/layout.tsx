import type { ReactNode } from 'react';
import Link from 'next/link';
import { Box } from 'lucide-react';

const DOCS_PAGES = [
  { title: 'Introduction', href: '/docs' },
  { title: 'Architecture & Design', href: '/docs/architecture' },
  { title: 'CLI Reference', href: '/docs/cli' },
  { title: 'Configuration', href: '/docs/configuration' },
  { title: 'MCP Setup', href: '/docs/mcp' },
  { title: 'Indexing Engine', href: '/docs/indexing' },
  { title: 'Web UI', href: '/docs/web-ui' },
  { title: 'Memory System', href: '/docs/memory' },
  { title: 'Wiki Management', href: '/docs/wiki' },
  { title: 'LLM Providers', href: '/docs/providers' },
  { title: 'Troubleshooting', href: '/docs/troubleshooting' },
  { title: 'Contributing', href: '/docs/contributing' },
];

export default function DocsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row">
      <aside className="w-full md:w-64 border-r border-white/10 bg-surface/30 p-6 flex-shrink-0 flex flex-col sticky top-0 md:h-screen overflow-y-auto">
        <Link href="/" className="flex items-center gap-2 mb-8">
          <div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center border border-primary/30">
            <Box className="w-5 h-5 text-primary" />
          </div>
          <span className="font-display font-bold text-xl tracking-tight text-text-primary">Synap</span>
        </Link>
        <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-4">Documentation</div>
        <nav className="flex flex-col gap-2">
          {DOCS_PAGES.map((page) => (
            <Link
              key={page.href}
              href={page.href}
              className="text-sm text-text-secondary hover:text-primary transition-colors py-1"
            >
              {page.title}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6 md:p-12 lg:p-24 overflow-y-auto max-w-4xl mx-auto w-full">
        <article className="prose prose-invert prose-headings:font-display prose-a:text-primary hover:prose-a:text-primary/80 prose-code:text-primary prose-code:bg-primary/10 prose-code:px-1 prose-code:rounded prose-pre:bg-surface prose-pre:border prose-pre:border-white/10 max-w-none">
          {children}
        </article>
      </main>
    </div>
  );
}
