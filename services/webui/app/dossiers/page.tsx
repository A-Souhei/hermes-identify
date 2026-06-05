'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { api, DossierOut } from '@/lib/api'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default function DossiersPage() {
  const router = useRouter()
  const [dossiers, setDossiers] = useState<DossierOut[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [showInput, setShowInput] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.dossiers.list().then(setDossiers).catch(() => setError('Failed to load dossiers')).finally(() => setLoading(false))
  }, [])

  async function handleCreate() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try {
      const d = await api.dossiers.create(name)
      router.push(`/dossiers/${d.id}`)
    } catch {
      setError('Failed to create dossier')
      setCreating(false)
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink-50">Dossiers</h1>
          <p className="text-ink-400 mt-1 text-sm">Curated assemblies of topics, entities, and images.</p>
        </div>
        {!showInput && (
          <button
            onClick={() => setShowInput(true)}
            className="btn-primary shrink-0"
          >
            New Dossier
          </button>
        )}
      </div>

      {showInput && (
        <div className="mb-6 surface border border-ink-700/60 rounded-xl p-4 flex gap-3 items-center">
          <input
            autoFocus
            type="text"
            placeholder="Dossier name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') { setShowInput(false); setNewName('') } }}
            className="flex-1 bg-transparent border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-500 focus:outline-none focus:border-amber-400/60"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newName.trim()}
            className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {creating ? 'Creating…' : 'Create'}
          </button>
          <button
            onClick={() => { setShowInput(false); setNewName('') }}
            className="px-3 py-2 rounded-lg text-sm font-medium text-ink-400 hover:text-ink-100 hover:bg-ink-800/60 transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <p className="text-ink-500 text-sm">Loading…</p>
      )}

      {!loading && dossiers.length === 0 && (
        <div className="surface border border-ink-700/60 rounded-xl p-10 text-center">
          <p className="text-ink-400 text-sm">No dossiers yet. Create one to get started.</p>
        </div>
      )}

      {!loading && dossiers.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {dossiers.map((d) => (
            <div key={d.id} className="surface border border-ink-700/60 rounded-xl p-5 flex flex-col gap-3">
              <div className="flex-1">
                <p className="text-ink-50 font-semibold text-base truncate">{d.name}</p>
                <p className="text-ink-500 text-xs mt-1">Created {formatDate(d.created_at)}</p>
              </div>
              <Link
                href={`/dossiers/${d.id}`}
                className="btn-primary text-center text-sm"
              >
                Open
              </Link>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
