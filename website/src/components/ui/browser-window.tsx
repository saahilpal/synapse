import React from "react"
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

interface BrowserWindowProps extends React.HTMLAttributes<HTMLDivElement> {
  url?: string
}

export function BrowserWindow({ children, className, url, ...props }: BrowserWindowProps) {
  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-xl border border-white/10 bg-surface shadow-2xl ring-1 ring-white/5",
        className
      )}
      {...props}
    >
      <div className="flex h-12 items-center gap-2 border-b border-white/5 bg-background/50 px-4">
        <div className="flex gap-1.5">
          <div className="h-3 w-3 rounded-full bg-red-500/20 ring-1 ring-inset ring-red-500/50" />
          <div className="h-3 w-3 rounded-full bg-yellow-500/20 ring-1 ring-inset ring-yellow-500/50" />
          <div className="h-3 w-3 rounded-full bg-green-500/20 ring-1 ring-inset ring-green-500/50" />
        </div>
        {url && (
          <div className="mx-auto flex h-6 w-full max-w-sm items-center justify-center rounded-md bg-white/5 px-3 text-xs text-text-secondary/60">
            {url}
          </div>
        )}
      </div>
      <div className="relative flex-1 bg-surface">{children}</div>
    </div>
  )
}
