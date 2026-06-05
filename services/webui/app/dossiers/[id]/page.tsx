'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api, DossierBlockResolved, DossierDetail, TopicIndex } from '@/lib/api'

const BLOCK_BADGE: Record<string, string> = {
  topic: 'bg-amber-400/20 text-amber-300',
  subtopic: 'bg-violet-400/20 text-violet-300',
  section: 'bg-emerald-500/20 text-emerald-300',
  entity: 'bg-sky-400/20 text-sky-300',
  image: 'bg-rose-500/20 text-rose-300',
}

function BlockCard({
  block,
  index,
  total,
  onMoveUp,
  onMoveDown,
  onRemove,
}: {
  block: DossierBlockResolved
  index: number
  total: number
  onMoveUp: () => void
  onMoveDown: () => void
  onRemove: () => void
}) {
  return (
    <div className="surface border border-ink-700/60 rounded-xl px-4 py-3 flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${BLOCK_BADGE[block.block_type] ?? 'bg-ink-700 text-ink-300'}`}>
            {block.block_type}
          </span>
        </div>
        <p className="text-ink-100 text-sm font-medium truncate">{block.label}</p>
        {typeof block.meta.description === 'string' && block.meta.description && (
          <p className="text-ink-500 text-xs mt-0.5 line-clamp-2">{block.meta.description}</p>
        )}
      </div>
      <div className="flex flex-col gap-1 shrink-0">
        <button
          disabled={index === 0}
          onClick={onMoveUp}
          className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Move up"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="18 15 12 9 6 15" />
          </svg>
        </button>
        <button
          disabled={index === total - 1}
          onClick={onMoveDown}
          className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Move down"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        <button
          onClick={onRemove}
          className="p-1 rounded text-ink-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
          title="Remove"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6M14 11v6" />
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
        </button>
      </div>
    </div>
  )
}

function TopicTree({
  index,
  onAdd,
  added,
}: {
  index: TopicIndex
  onAdd: (blockType: string, refId: string) => void
  added: Set<string>
}) {
  const [expandedSubtopics, setExpandedSubtopics] = useState<Set<string>>(new Set())
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())

  function toggleSubtopic(id: string) {
    setExpandedSubtopics((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleSection(id: string) {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="text-sm">
      <div className="flex items-center gap-2 py-1.5">
        <span className="text-ink-100 font-semibold truncate">{index.topic_name}</span>
      </div>
      {index.subtopics.map((st) => (
        <div key={st.id} className="ml-3 border-l border-ink-700/60 pl-3">
          <div className="flex items-center gap-2 py-1">
            <button
              onClick={() => toggleSubtopic(st.id)}
              className="text-ink-400 hover:text-ink-200 transition-colors"
            >
              <svg className={`w-3 h-3 transition-transform ${expandedSubtopics.has(st.id) ? 'rotate-90' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
            <span className="flex-1 text-ink-300 truncate">{st.name}</span>
            <button
              onClick={() => onAdd('subtopic', st.id)}
              disabled={added.has(st.id)}
              className="shrink-0 text-xs px-2 py-0.5 rounded bg-violet-400/10 text-violet-300 hover:bg-violet-400/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              {added.has(st.id) ? '✓' : '+ Add'}
            </button>
          </div>
          {expandedSubtopics.has(st.id) && st.sections.map((sec) => (
            <div key={sec.id} className="ml-3 border-l border-ink-700/60 pl-3">
              <div className="flex items-center gap-2 py-1">
                <button
                  onClick={() => toggleSection(sec.id)}
                  className="text-ink-400 hover:text-ink-200 transition-colors"
                >
                  <svg className={`w-3 h-3 transition-transform ${expandedSections.has(sec.id) ? 'rotate-90' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
                <span className="flex-1 text-ink-300 truncate text-xs">{sec.name}</span>
                <button
                  onClick={() => onAdd('section', sec.id)}
                  disabled={added.has(sec.id)}
                  className="shrink-0 text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  {added.has(sec.id) ? '✓' : '+ Add'}
                </button>
              </div>
              {expandedSections.has(sec.id) && sec.entities.map((ent) => (
                <div key={ent.id} className="ml-3 border-l border-ink-700/60 pl-3 flex items-center gap-2 py-1">
                  <span className="flex-1 text-ink-400 text-xs truncate">{ent.name}</span>
                  <button
                    onClick={() => onAdd('entity', ent.id)}
                    disabled={added.has(ent.id)}
                    className="shrink-0 text-xs px-2 py-0.5 rounded bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    {added.has(ent.id) ? '✓' : '+ Add'}
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export default function DossierDetailPage() {
  const params = useParams()
  const router = useRouter()
  const id = params.id as string

  const [dossier, setDossier] = useState<DossierDetail | null>(null)
  const [topicIndices, setTopicIndices] = useState<TopicIndex[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editingName, setEditingName] = useState(false)
  const [nameValue, setNameValue] = useState('')
  const nameInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    Promise.all([
      api.dossiers.get(id),
      api.topics.list().then(async (topics) => {
        return Promise.all(topics.map((t) => api.topics.index(t.id)))
      }),
    ])
      .then(([d, indices]) => {
        setDossier(d)
        setNameValue(d.name)
        setTopicIndices(indices)
      })
      .catch(() => setError('Failed to load dossier'))
      .finally(() => setLoading(false))
  }, [id])

  async function saveName() {
    if (!dossier || nameValue.trim() === dossier.name) {
      setEditingName(false)
      return
    }
    try {
      const updated = await api.dossiers.rename(id, nameValue.trim())
      setDossier((prev) => prev ? { ...prev, name: updated.name } : prev)
    } catch {
      setNameValue(dossier.name)
    }
    setEditingName(false)
  }

  async function addBlock(blockType: string, refId: string) {
    if (!dossier) return
    try {
      const block = await api.dossiers.addBlock(id, {
        block_type: blockType,
        ref_id: refId,
        order_index: dossier.blocks.length,
      })
      setDossier((prev) => prev ? { ...prev, blocks: [...prev.blocks, block] } : prev)
    } catch {
      // silent — block might already exist or ref not found
    }
  }

  async function removeBlock(blockId: string) {
    if (!dossier) return
    try {
      await api.dossiers.removeBlock(id, blockId)
      setDossier((prev) =>
        prev ? { ...prev, blocks: prev.blocks.filter((b) => b.id !== blockId) } : prev
      )
    } catch {
      // silent
    }
  }

  async function moveBlock(index: number, direction: -1 | 1) {
    if (!dossier) return
    const blocks = [...dossier.blocks]
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= blocks.length) return

    const current = blocks[index]
    const neighbor = blocks[targetIndex]

    try {
      const [updatedCurrent, updatedNeighbor] = await Promise.all([
        api.dossiers.reorderBlock(id, current.id, neighbor.order_index),
        api.dossiers.reorderBlock(id, neighbor.id, current.order_index),
      ])
      const newBlocks = blocks.map((b) => {
        if (b.id === current.id) return updatedCurrent
        if (b.id === neighbor.id) return updatedNeighbor
        return b
      })
      newBlocks.sort((a, b) => a.order_index - b.order_index)
      setDossier((prev) => prev ? { ...prev, blocks: newBlocks } : prev)
    } catch {
      // silent
    }
  }

  if (loading) {
    return <main className="p-6"><p className="text-ink-500 text-sm">Loading…</p></main>
  }

  if (error || !dossier) {
    return (
      <main className="p-6">
        <p className="text-rose-400 text-sm">{error ?? 'Dossier not found'}</p>
        <button onClick={() => router.push('/dossiers')} className="mt-4 btn-primary">Back to Dossiers</button>
      </main>
    )
  }

  return (
    <main className="p-6 max-w-7xl mx-auto">
      <div className="mb-6 flex items-center gap-3">
        <button
          onClick={() => router.push('/dossiers')}
          className="text-ink-400 hover:text-ink-100 transition-colors"
          title="Back"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        {editingName ? (
          <input
            ref={nameInputRef}
            value={nameValue}
            onChange={(e) => setNameValue(e.target.value)}
            onBlur={saveName}
            onKeyDown={(e) => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') { setNameValue(dossier.name); setEditingName(false) } }}
            className="text-2xl font-bold bg-transparent border-b border-amber-400/60 text-ink-50 focus:outline-none flex-1"
            autoFocus
          />
        ) : (
          <h1
            className="text-2xl font-bold text-ink-50 cursor-pointer hover:text-amber-200 transition-colors"
            onClick={() => { setEditingName(true); setTimeout(() => nameInputRef.current?.focus(), 0) }}
            title="Click to rename"
          >
            {dossier.name}
          </h1>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left panel — hierarchy browser */}
        <div>
          <h2 className="text-sm font-semibold text-ink-300 mb-3 uppercase tracking-wide">Add content</h2>
          <div className="surface border border-ink-700/60 rounded-xl p-4 max-h-[70vh] overflow-y-auto space-y-4">
            {topicIndices.length === 0 && (
              <p className="text-ink-500 text-sm">No topics found.</p>
            )}
            {topicIndices.map((index) => (
              <TopicTree key={index.topic_id} index={index} onAdd={addBlock} added={new Set(dossier.blocks.map((b) => b.ref_id))} />
            ))}
          </div>
        </div>

        {/* Right panel — dossier blocks */}
        <div>
          <h2 className="text-sm font-semibold text-ink-300 mb-3 uppercase tracking-wide">
            Dossier blocks
            {dossier.blocks.length > 0 && (
              <span className="ml-2 text-ink-500 normal-case font-normal">{dossier.blocks.length} item{dossier.blocks.length !== 1 ? 's' : ''}</span>
            )}
          </h2>
          <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
            {dossier.blocks.length === 0 && (
              <div className="surface border border-ink-700/60 rounded-xl p-8 text-center">
                <p className="text-ink-500 text-sm">No blocks yet — add content from the left panel.</p>
              </div>
            )}
            {dossier.blocks.map((block, i) => (
              <BlockCard
                key={block.id}
                block={block}
                index={i}
                total={dossier.blocks.length}
                onMoveUp={() => moveBlock(i, -1)}
                onMoveDown={() => moveBlock(i, 1)}
                onRemove={() => removeBlock(block.id)}
              />
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
