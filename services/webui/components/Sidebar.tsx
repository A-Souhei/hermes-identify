'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { ThemeToggle } from './ThemeToggle'

interface HealthData {
  version?: string
}

interface NavItem {
  key: string
  label: string
  href: string
  icon: React.ReactNode
}

const NAV_ITEMS: NavItem[] = [
  {
    key: 'topics',
    label: 'Topics',
    href: '/topics',
    icon: (
      <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" />
        <path d="M8 21h8M12 17v4" />
        <path d="M7 7h4M7 11h10" />
      </svg>
    ),
  },
]

export function Sidebar({ active }: { active: string }) {
  const [health, setHealth] = useState<'loading' | 'ok' | 'error'>('loading')
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/entifier/health')
      .then((r) => {
        if (!r.ok) throw new Error('not ok')
        return r.json() as Promise<HealthData>
      })
      .then((data) => {
        setVersion(data.version ?? null)
        setHealth('ok')
      })
      .catch(() => setHealth('error'))
  }, [])

  return (
    <aside className="lg:w-56 lg:shrink-0 lg:sticky lg:top-0 lg:h-screen flex flex-col surface border-r border-ink-700/60 relative">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-ink-700/60">
        {/* Logo */}
        <div className="w-8 h-8 rounded-lg bg-amber-400 flex items-center justify-center shrink-0">
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none">
            {/* Open book with amber spine */}
            <rect x="2" y="5" width="9" height="14" rx="1" fill="currentColor" className="text-amber-900" opacity="0.7" />
            <rect x="13" y="5" width="9" height="14" rx="1" fill="currentColor" className="text-amber-900" opacity="0.7" />
            <rect x="10.5" y="4" width="3" height="16" rx="0.5" fill="currentColor" className="text-amber-900" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-ink-50 leading-none truncate">hermes-identify</p>
          <p className="text-[11px] text-ink-400 mt-0.5 truncate">Entity extraction</p>
        </div>
        <ThemeToggle />
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        <p className="label-eyebrow px-2 mb-2">Navigation</p>
        {NAV_ITEMS.map((item) => {
          const isActive = active === item.key
          return (
            <Link
              key={item.key}
              href={item.href}
              className={[
                'relative flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-amber-400/10 text-amber-200 ring-1 ring-amber-400/20'
                  : 'text-ink-300 hover:text-ink-50 hover:bg-ink-800/60',
              ].join(' ')}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-amber-400 rounded-r-full" />
              )}
              {item.icon}
              {item.label}
            </Link>
          )
        })}
      </nav>

      {/* Health status */}
      <div className="absolute bottom-0 left-0 right-0 border-t border-ink-700/60 px-4 py-3 flex items-center gap-2.5">
        <span
          className={[
            'w-2 h-2 rounded-full shrink-0',
            health === 'ok' ? 'bg-emerald-400' : health === 'error' ? 'bg-rose-400' : 'bg-ink-500 animate-pulse',
          ].join(' ')}
        />
        <div className="min-w-0">
          <p className="text-xs font-medium text-ink-200 leading-none">Entifier</p>
          <p className="text-[11px] text-ink-500 mt-0.5 truncate">
            {health === 'loading' && 'Checking…'}
            {health === 'ok' && (version ? `v${version}` : 'reachable')}
            {health === 'error' && 'unreachable'}
          </p>
        </div>
      </div>
    </aside>
  )
}
