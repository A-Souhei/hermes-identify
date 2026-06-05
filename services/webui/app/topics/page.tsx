'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'
import { api, Topic } from '@/lib/api'
import { relativeTime } from '@/lib/format'

function TopicCard({ topic }: { topic: Topic }) {
  return (
    <div className="card-hover p-5 flex flex-col gap-3">
      <div className="flex-1 min-w-0 space-y-1">
        <h2 className="font-semibold text-ink-50 leading-snug truncate">{topic.name}</h2>
        {topic.description ? (
          <p className="text-ink-400 text-sm line-clamp-2">{topic.description}</p>
        ) : (
          <p className="text-ink-600 text-sm italic">No description</p>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-ink-700/60">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            href={`/topics/${encodeURIComponent(topic.id)}`}
            className="btn-ghost text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1"
          >
            Browse
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </Link>
          <span className="chip-mono truncate max-w-[120px]">{topic.id}</span>
        </div>
        <span className="text-[11px] text-ink-500 shrink-0">{relativeTime(topic.created_at)}</span>
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="card p-5 flex flex-col gap-3 animate-pulse">
      <div className="h-5 bg-ink-700/60 rounded w-2/3" />
      <div className="space-y-1.5">
        <div className="h-3.5 bg-ink-700/40 rounded w-full" />
        <div className="h-3.5 bg-ink-700/40 rounded w-4/5" />
      </div>
      <div className="flex items-center gap-2 pt-1 border-t border-ink-700/60">
        <div className="h-6 bg-ink-700/40 rounded w-16" />
        <div className="h-5 bg-ink-700/40 rounded w-24" />
      </div>
    </div>
  )
}

interface Toast {
  id: number
  message: string
  type: 'success' | 'error'
}

export default function TopicsPage() {
  const [topics, setTopics] = useState<Topic[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = React.useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = (message: string, type: Toast['type']) => {
    const id = Date.now()
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500)
  }

  async function loadTopics(signal?: AbortSignal) {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await api.topics.list()
      setTopics(data)
    } catch (err) {
      if (signal?.aborted) return
      setLoadError(err instanceof Error ? err.message : 'Failed to load topics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    loadTopics(controller.signal)
    return () => controller.abort()
  }, [])

  const openModal = () => {
    setName('')
    setDescription('')
    setModalError(null)
    setShowModal(true)
  }

  const closeModal = () => {
    if (creating) return
    setShowModal(false)
  }

  const handleCreate = async () => {
    if (creating) return
    if (!name.trim()) return
    setCreating(true)
    setModalError(null)
    try {
      const topic = await api.topics.create(name.trim(), description.trim() || undefined)
      setTopics((prev) => [topic, ...prev])
      addToast('Topic created', 'success')
      setShowModal(false)
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setCreating(false)
    }
  }

  return (
    <main className="px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">Topics</h1>
          <p className="mt-1 text-ink-400 text-sm">Organize your knowledge extraction projects.</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={loadTopics} className="btn-ghost" title="Refresh" disabled={loading}>
            <svg
              className={['w-4 h-4', loading ? 'animate-spin' : ''].join(' ')}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
            </svg>
            Refresh
          </button>
          <button onClick={openModal} className="btn-primary">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New topic
          </button>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : !loading && loadError ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-6 text-center">
          <p className="text-sm text-rose-300 mb-3">{loadError}</p>
          <button className="btn-secondary text-xs" onClick={() => loadTopics()}>Retry</button>
        </div>
      ) : topics.length === 0 ? (
        <div className="empty flex flex-col items-center gap-4">
          <svg className="w-10 h-10 text-ink-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 17v4M7 8h4M7 11h10" />
          </svg>
          <div>
            <p className="font-medium text-ink-300">No topics yet</p>
            <p className="text-ink-500 text-xs mt-0.5">Create your first topic to get started.</p>
          </div>
          <button onClick={openModal} className="btn-primary">
            Create your first topic
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {topics.map((t) => (
            <TopicCard key={t.id} topic={t} />
          ))}
        </div>
      )}

      {/* Create modal */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-975/60 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) closeModal() }}
        >
          <div className="card w-full max-w-md p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-ink-50">New topic</h2>
              <button onClick={closeModal} className="btn-ghost p-1" disabled={creating}>
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-eyebrow mb-1.5 block" htmlFor="topic-name">Name</label>
                <input
                  id="topic-name"
                  className="input"
                  placeholder="e.g. Climate Research"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={200}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreate() }}
                  autoFocus
                  disabled={creating}
                />
              </div>
              <div>
                <label className="label-eyebrow mb-1.5 block" htmlFor="topic-desc">Description <span className="text-ink-500 normal-case font-normal tracking-normal">(optional)</span></label>
                <textarea
                  id="topic-desc"
                  className="input resize-none"
                  rows={3}
                  placeholder="What is this topic about?"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={2000}
                  disabled={creating}
                />
              </div>
            </div>

            {modalError && (
              <p className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-md px-3 py-2">
                {modalError}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button onClick={closeModal} className="btn-secondary" disabled={creating}>Cancel</button>
              <button
                onClick={handleCreate}
                className="btn-primary min-w-[80px]"
                disabled={!name.trim() || creating}
              >
                {creating ? (
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 12a9 9 0 1 1-9-9" />
                  </svg>
                ) : (
                  'Create'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toasts */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={[
              'px-4 py-2.5 rounded-lg text-sm font-medium shadow-lg border pointer-events-auto',
              t.type === 'success'
                ? 'bg-emerald-950 border-emerald-500/30 text-emerald-200'
                : 'bg-rose-950 border-rose-500/30 text-rose-200',
            ].join(' ')}
          >
            {t.message}
          </div>
        ))}
      </div>
    </main>
  )
}
