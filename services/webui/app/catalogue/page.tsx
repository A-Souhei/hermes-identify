'use client'

import Link from 'next/link'
import { useEffect, useState, useCallback, useRef } from 'react'
import { api, Topic, TopicIndex } from '@/lib/api'
import CatalogueGraph from '@/components/CatalogueGraph'

const ENTITY_TYPE_COLORS: Record<string, { dot: string; label: string }> = {
  concept:      { dot: 'bg-blue-400',   label: 'text-blue-300' },
  methodology:  { dot: 'bg-purple-400', label: 'text-purple-300' },
  data_source:  { dot: 'bg-green-400',  label: 'text-green-300' },
  case_study:   { dot: 'bg-orange-400', label: 'text-orange-300' },
  finding:      { dot: 'bg-amber-400',  label: 'text-amber-300' },
  framework:    { dot: 'bg-rose-400',   label: 'text-rose-300' },
}

function SkeletonRow() {
  return <div className="h-12 animate-pulse bg-ink-800/50 rounded-xl" />
}

export default function CataloguePage() {
  const [topics, setTopics] = useState<Topic[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [view, setView] = useState<'tree' | 'graph'>('tree')

  const [indexCache, setIndexCache] = useState<Record<string, TopicIndex>>({})
  const [indexLoading, setIndexLoading] = useState<Record<string, boolean>>({})
  const [indexError, setIndexError] = useState<Record<string, string>>({})

  const [topicsOpen, setTopicsOpen] = useState<Record<string, boolean>>({})
  const [subtopicsOpen, setSubtopicsOpen] = useState<Record<string, boolean>>({})
  const [sectionsOpen, setSectionsOpen] = useState<Record<string, boolean>>({})

  // Sync refs for stable callbacks — avoids stale closures in useCallback deps
  const mountedRef = useRef(true)
  const loadingIdsRef = useRef<Set<string>>(new Set())  // sync in-flight tracker
  const cachedIdsRef = useRef<Set<string>>(new Set())   // sync cached tracker
  const indexCacheRef = useRef<Record<string, TopicIndex>>({})
  const expandAllActiveRef = useRef(false)
  const topicsOpenRef = useRef<Record<string, boolean>>({})
  const refreshTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  useEffect(() => { indexCacheRef.current = indexCache }, [indexCache])
  useEffect(() => { topicsOpenRef.current = topicsOpen }, [topicsOpen])
  useEffect(() => { return () => { mountedRef.current = false } }, [])

  // ── Load topics ─────────────────────────────────────────────────────────────

  const loadTopics = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await api.topics.list()
      if (signal?.aborted) return
      setTopics(data)
      // Invalidate index cache so fresh expands refetch
      setIndexCache({})
      setIndexError({})
      cachedIdsRef.current.clear()
    } catch (err) {
      if (signal?.aborted) return
      setLoadError(err instanceof Error ? err.message : 'Failed to load topics')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadTopics(controller.signal)
    return () => controller.abort()
  }, [loadTopics])

  // ── Load a single topic's index ──────────────────────────────────────────────
  // Stable callback — dedup via refs, not state, to avoid stale closure issues.

  const loadIndex = useCallback(async (topicId: string) => {
    if (cachedIdsRef.current.has(topicId) || loadingIdsRef.current.has(topicId)) return
    loadingIdsRef.current.add(topicId)
    setIndexLoading(prev => ({ ...prev, [topicId]: true }))
    setIndexError(prev => { const n = { ...prev }; delete n[topicId]; return n })
    try {
      const data = await api.topics.index(topicId)
      if (!mountedRef.current) return
      cachedIdsRef.current.add(topicId)
      setIndexCache(prev => ({ ...prev, [topicId]: data }))
      // Sections default-open when first loaded
      setSectionsOpen(prev => {
        const next = { ...prev }
        for (const sub of data.subtopics) {
          for (const sec of sub.sections) {
            next[sec.id] = true
          }
        }
        return next
      })
      // If "Expand all" was in progress, also open these subtopics
      if (expandAllActiveRef.current) {
        setSubtopicsOpen(prev => {
          const next = { ...prev }
          for (const sub of data.subtopics) { next[sub.id] = true }
          return next
        })
      }
    } catch (err) {
      if (!mountedRef.current) return
      setIndexError(prev => ({
        ...prev,
        [topicId]: err instanceof Error ? err.message : 'Failed to load index',
      }))
    } finally {
      loadingIdsRef.current.delete(topicId)
      if (mountedRef.current) {
        setIndexLoading(prev => { const n = { ...prev }; delete n[topicId]; return n })
      }
    }
  }, []) // stable — all mutable state accessed via refs

  // ── Live update via BroadcastChannel ────────────────────────────────────────
  // Ingest tab posts { type: 'topic-updated', topicId } after each upload.
  // Debounce per topic (4 s) so a batch of rapid uploads triggers one refresh.

  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const bc = new BroadcastChannel('hermes-ingest')
    bc.onmessage = (e) => {
      if (e.data?.type !== 'topic-updated') return
      const topicId = e.data.topicId as string
      if (!topicId) return
      if (refreshTimersRef.current[topicId]) clearTimeout(refreshTimersRef.current[topicId])
      refreshTimersRef.current[topicId] = setTimeout(() => {
        delete refreshTimersRef.current[topicId]
        if (!mountedRef.current) return
        cachedIdsRef.current.delete(topicId)
        setIndexCache(prev => { const n = { ...prev }; delete n[topicId]; return n })
        if (topicsOpenRef.current[topicId]) loadIndex(topicId)
      }, 4000)
    }
    return () => {
      bc.close()
      Object.values(refreshTimersRef.current).forEach(clearTimeout)
    }
  }, [loadIndex])

  // ── Toggle handlers ──────────────────────────────────────────────────────────

  const toggleTopic = useCallback((topicId: string) => {
    setTopicsOpen(prev => {
      const next = { ...prev, [topicId]: !prev[topicId] }
      if (next[topicId]) loadIndex(topicId)
      return next
    })
  }, [loadIndex])

  const toggleSubtopic = useCallback((subtopicId: string) => {
    setSubtopicsOpen(prev => ({ ...prev, [subtopicId]: !prev[subtopicId] }))
  }, [])

  const toggleSection = useCallback((sectionId: string) => {
    setSectionsOpen(prev => ({ ...prev, [sectionId]: !prev[sectionId] }))
  }, [])

  // ── Global expand / collapse ─────────────────────────────────────────────────

  const expandAll = useCallback(() => {
    expandAllActiveRef.current = true
    const nextTopics: Record<string, boolean> = {}
    const nextSubtopics: Record<string, boolean> = {}
    for (const topic of topics) {
      nextTopics[topic.id] = true
      // Open subtopics for already-cached topics synchronously
      const cached = indexCacheRef.current[topic.id]
      if (cached) {
        for (const sub of cached.subtopics) { nextSubtopics[sub.id] = true }
      }
      // For uncached topics, loadIndex will open subtopics on completion (via expandAllActiveRef)
      loadIndex(topic.id)
    }
    setTopicsOpen(nextTopics)
    setSubtopicsOpen(prev => ({ ...prev, ...nextSubtopics }))
  }, [topics, loadIndex])

  const collapseAll = useCallback(() => {
    expandAllActiveRef.current = false
    setTopicsOpen({})
    setSubtopicsOpen({})
    setSectionsOpen({})
  }, [])

  const retryIndex = useCallback((topicId: string) => {
    // Clear cached/loading flags so loadIndex re-runs
    cachedIdsRef.current.delete(topicId)
    loadingIdsRef.current.delete(topicId)
    setIndexError(prev => { const n = { ...prev }; delete n[topicId]; return n })
    loadIndex(topicId)
  }, [loadIndex])

  return (
    <main className="px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">Catalogue</h1>
          <p className="mt-1 text-ink-400 text-sm">Full index of all topics, subtopics, sections and entities.</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={expandAll} className="btn-ghost text-xs" disabled={loading}>Expand all</button>
          <button onClick={collapseAll} className="btn-ghost text-xs" disabled={loading}>Collapse all</button>
          <button onClick={() => loadTopics()} className="btn-ghost" title="Refresh" disabled={loading}>
            <svg
              className={['w-4 h-4', loading ? 'animate-spin' : ''].join(' ')}
              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Tab bar */}
      {topics.length > 0 && !loading && (
        <div className="flex items-center gap-1 mb-6">
          <button
            onClick={() => setView('tree')}
            className={['px-3 py-1.5 rounded-lg text-sm font-medium transition-colors', view === 'tree' ? 'bg-amber-400/10 text-amber-400' : 'btn-ghost'].join(' ')}
          >
            Tree
          </button>
          <button
            onClick={() => setView('graph')}
            className={['px-3 py-1.5 rounded-lg text-sm font-medium transition-colors', view === 'graph' ? 'bg-amber-400/10 text-amber-400' : 'btn-ghost'].join(' ')}
          >
            Graph
          </button>
        </div>
      )}

      {/* Graph — always mounted once topics are ready so Three.js state survives tab switches */}
      {topics.length > 0 && !loading && (
        <div className={view === 'graph' ? '' : 'hidden'}>
          <CatalogueGraph topics={topics} />
        </div>
      )}

      {/* Content */}
      {view !== 'graph' && (loading ? (
        <div className="space-y-2">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : loadError ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-6 text-center">
          <p className="text-sm text-rose-300 mb-3">{loadError}</p>
          <button className="btn-secondary text-xs" onClick={() => loadTopics()}>Retry</button>
        </div>
      ) : topics.length === 0 ? (
        <div className="empty flex flex-col items-center gap-4">
          <svg className="w-10 h-10 text-ink-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3v4M8 7H4a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h4M16 7h4a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1h-4M8 11v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2M9 14v3M15 14v3M6 17h4M14 17h4" />
          </svg>
          <div>
            <p className="font-medium text-ink-300">No topics yet</p>
            <p className="text-ink-500 text-xs mt-0.5">Create your first topic to get started.</p>
          </div>
          <Link href="/topics" className="btn-primary">Go to Topics</Link>
        </div>
      ) : (
        <div className="divide-y divide-ink-800">
          {topics.map((topic) => {
            const isOpen = !!topicsOpen[topic.id]
            const isLoadingIndex = !!indexLoading[topic.id]
            const error = indexError[topic.id]
            const index = indexCache[topic.id]
            const subtopicCount = index?.subtopics.length ?? null

            return (
              <div key={topic.id}>
                {/* Topic row */}
                <div
                  className="flex items-center gap-3 py-3 cursor-pointer hover:bg-ink-800/30 transition-colors rounded-lg px-2 -mx-2"
                  onClick={() => toggleTopic(topic.id)}
                  role="button"
                  aria-expanded={isOpen}
                >
                  <svg
                    className={['w-4 h-4 shrink-0 text-ink-400 transition-transform', isOpen ? 'rotate-90' : ''].join(' ')}
                    viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round"
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                  {index && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />}
                  <span className="font-medium text-ink-100 flex-1 min-w-0 truncate">{topic.name}</span>
                  {topic.description && (
                    <span className="text-ink-500 text-sm truncate max-w-[280px] hidden sm:block">{topic.description}</span>
                  )}
                  {!isOpen && subtopicCount !== null && (
                    <span className="text-xs text-ink-500 shrink-0">{subtopicCount} subtopic{subtopicCount !== 1 ? 's' : ''}</span>
                  )}
                  {!isOpen && subtopicCount === null && !isLoadingIndex && (
                    <span className="text-xs text-ink-600 shrink-0">click to load</span>
                  )}
                  {isLoadingIndex && (
                    <svg className="w-4 h-4 animate-spin text-ink-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 12a9 9 0 1 1-9-9" />
                    </svg>
                  )}
                </div>

                {/* Topic body */}
                {isOpen && (
                  <div className="pb-2">
                    {error && (
                      <div className="ml-7 flex items-center gap-3 py-2 text-sm text-rose-400">
                        <span>{error}</span>
                        <button
                          className="btn-ghost text-xs text-rose-400 hover:text-rose-300"
                          onClick={(e) => { e.stopPropagation(); retryIndex(topic.id) }}
                        >
                          Retry
                        </button>
                      </div>
                    )}

                    {!error && !isLoadingIndex && index && index.subtopics.length === 0 && (
                      <p className="ml-7 py-2 text-sm italic text-ink-600">No subtopics</p>
                    )}

                    {!error && index && index.subtopics.map((sub) => {
                      const subOpen = !!subtopicsOpen[sub.id]
                      const totalEntities = sub.sections.reduce((n, s) => n + s.entities.length, 0)

                      return (
                        <div key={sub.id} className="ml-4 pl-4 border-l border-ink-800">
                          {/* Subtopic row */}
                          <div
                            className="flex items-center gap-3 py-2 cursor-pointer hover:bg-ink-800/30 transition-colors rounded-lg px-2 -mx-2"
                            onClick={() => toggleSubtopic(sub.id)}
                            role="button"
                            aria-expanded={subOpen}
                          >
                            <svg
                              className={['w-3.5 h-3.5 shrink-0 text-ink-500 transition-transform', subOpen ? 'rotate-90' : ''].join(' ')}
                              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                              strokeLinecap="round" strokeLinejoin="round"
                            >
                              <path d="M9 18l6-6-6-6" />
                            </svg>
                            <span className="text-sm font-medium text-ink-200 flex-1 min-w-0 truncate">{sub.name}</span>
                            {!subOpen && (
                              <span className="text-xs text-ink-500 shrink-0">
                                {sub.sections.length} section{sub.sections.length !== 1 ? 's' : ''} · {totalEntities} entit{totalEntities !== 1 ? 'ies' : 'y'}
                              </span>
                            )}
                          </div>

                          {/* Subtopic body */}
                          {subOpen && (
                            <div>
                              {sub.sections.length === 0 && (
                                <p className="ml-7 py-1.5 text-sm italic text-ink-600">No sections</p>
                              )}

                              {sub.sections.map((sec) => {
                                // Sections seed to true in loadIndex; !!undefined = false (closed after collapseAll)
                                const secOpen = !!sectionsOpen[sec.id]

                                return (
                                  <div key={sec.id} className="ml-4 pl-4 border-l border-ink-800">
                                    {/* Section row */}
                                    <div
                                      className="flex items-center gap-3 py-1.5 cursor-pointer hover:bg-ink-800/30 transition-colors rounded-lg px-2 -mx-2"
                                      onClick={() => toggleSection(sec.id)}
                                      role="button"
                                      aria-expanded={secOpen}
                                    >
                                      <svg
                                        className={['w-3 h-3 shrink-0 text-ink-600 transition-transform', secOpen ? 'rotate-90' : ''].join(' ')}
                                        viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                                        strokeLinecap="round" strokeLinejoin="round"
                                      >
                                        <path d="M9 18l6-6-6-6" />
                                      </svg>
                                      <span className="text-xs font-medium text-ink-300 flex-1 min-w-0 truncate">{sec.name}</span>
                                      {!secOpen && (
                                        <span className="text-xs text-ink-600 shrink-0">
                                          {sec.entities.length} entit{sec.entities.length !== 1 ? 'ies' : 'y'}
                                        </span>
                                      )}
                                    </div>

                                    {/* Entities */}
                                    {secOpen && (
                                      <div className="flex flex-wrap gap-1.5 py-2 ml-6">
                                        {sec.entities.length === 0 ? (
                                          <p className="text-xs italic text-ink-600">No entities</p>
                                        ) : (
                                          sec.entities.map((ent) => {
                                            const colors = ent.entity_type ? ENTITY_TYPE_COLORS[ent.entity_type] : undefined
                                            return (
                                              <span
                                                key={ent.id}
                                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-ink-800 text-ink-200 text-xs font-mono"
                                                title={ent.entity_type ?? undefined}
                                              >
                                                <span className={['w-1.5 h-1.5 rounded-full shrink-0', colors ? colors.dot : 'bg-ink-500'].join(' ')} />
                                                <span className={colors ? colors.label : 'text-ink-400'}>{ent.name}</span>
                                              </span>
                                            )
                                          })
                                        )}
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ))}
    </main>
  )
}
