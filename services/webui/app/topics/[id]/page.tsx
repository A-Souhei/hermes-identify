'use client'

import Link from 'next/link'
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, Document, Entity, Image, SubTopic, TopicIndex, Topic, SearchResponse } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import { Lightbox } from '@/components/Lightbox'

// ── Helpers ──────────────────────────────────────────────────────────────────

const MAX_DOC_BYTES = 25 * 1024 * 1024
const MAX_IMG_BYTES = 10 * 1024 * 1024
const DOC_EXTS = new Set(['.pdf', '.md', '.csv', '.json', '.yaml', '.yml'])
const IMG_EXTS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.gif'])

const ENTITY_TYPE_COLORS: Record<string, { dot: string; label: string }> = {
  concept:      { dot: 'bg-blue-400',   label: 'text-blue-300' },
  methodology:  { dot: 'bg-purple-400', label: 'text-purple-300' },
  data_source:  { dot: 'bg-green-400',  label: 'text-green-300' },
  case_study:   { dot: 'bg-orange-400', label: 'text-orange-300' },
  finding:      { dot: 'bg-amber-400',  label: 'text-amber-300' },
  framework:    { dot: 'bg-rose-400',   label: 'text-rose-300' },
}

function EntityTypeBadge({ type }: { type: string | null }) {
  if (!type) return null
  const colors = ENTITY_TYPE_COLORS[type] ?? { dot: 'bg-ink-500', label: 'text-ink-400' }
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${colors.label}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${colors.dot}`} />
      {type}
    </span>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────

interface Toast {
  id: number
  message: string
  type: 'success' | 'error'
}

function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const addToast = useCallback((message: string, type: Toast['type']) => {
    const id = Date.now()
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500)
  }, [])
  return { toasts, addToast }
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={`animate-pulse bg-ink-700/50 rounded ${className ?? ''}`} />
}

// ── Subtopics Sidebar ─────────────────────────────────────────────────────────

function SubtopicsSidebar({
  subtopics,
  activeId,
  onSelect,
}: {
  subtopics: SubTopic[]
  activeId: string | null
  onSelect: (id: string | null) => void
}) {
  return (
    <aside className="w-56 shrink-0 border-r border-ink-800 flex flex-col">
      <p className="label-eyebrow px-4 pt-5 pb-3">Subtopics</p>
      <nav className="flex-1 overflow-y-auto">
        {/* All row */}
        <button
          onClick={() => onSelect(null)}
          className={[
            'w-full text-left px-4 py-2 text-sm transition-colors',
            activeId === null
              ? 'border-l-2 border-amber-400 bg-amber-400/10 text-amber-200'
              : 'border-l-2 border-transparent text-ink-400 hover:text-ink-100',
          ].join(' ')}
        >
          All
        </button>

        {subtopics.length === 0 ? (
          <p className="px-4 py-2 text-xs text-ink-600 italic">None yet</p>
        ) : (
          subtopics.map((st) => (
            <button
              key={st.id}
              onClick={() => onSelect(st.id)}
              className={[
                'w-full text-left px-4 py-2 text-sm transition-colors truncate',
                activeId === st.id
                  ? 'border-l-2 border-amber-400 bg-amber-400/10 text-amber-200'
                  : 'border-l-2 border-transparent text-ink-400 hover:text-ink-100',
              ].join(' ')}
              title={st.name}
            >
              {st.name}
            </button>
          ))
        )}
      </nav>
    </aside>
  )
}

// ── Index Tab ─────────────────────────────────────────────────────────────────

function IndexTab({ topicIndex }: { topicIndex: TopicIndex | null }) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  if (!topicIndex || topicIndex.subtopics.length === 0) {
    return (
      <p className="text-ink-500 text-sm italic py-8 text-center">
        No index yet — run the pipeline to generate one.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      {topicIndex.subtopics.map((st) => {
        const isCollapsed = collapsed[st.id] ?? false
        return (
          <div key={st.id} className="border border-ink-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setCollapsed((prev) => ({ ...prev, [st.id]: !isCollapsed }))}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-ink-800/40 transition-colors"
            >
              <div className="text-left min-w-0">
                <p className="font-bold text-ink-50 leading-snug truncate">{st.name}</p>
                {st.description && (
                  <p className="text-xs text-ink-400 mt-0.5 truncate">{st.description}</p>
                )}
              </div>
              <svg
                className={`w-4 h-4 text-ink-500 shrink-0 ml-3 transition-transform ${isCollapsed ? '-rotate-90' : ''}`}
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round"
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>

            {!isCollapsed && (
              <div className="px-4 pb-4 space-y-4 border-t border-ink-800">
                {st.sections.length === 0 ? (
                  <p className="text-xs text-ink-600 italic pt-3">No sections</p>
                ) : (
                  st.sections.map((sec) => (
                    <div key={sec.id} className="pt-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                        <span className="font-medium text-ink-100 text-sm">{sec.name}</span>
                      </div>
                      {sec.description && (
                        <p className="text-ink-400 text-xs mb-2 ml-3.5">{sec.description}</p>
                      )}
                      {sec.entities.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 ml-3.5">
                          {sec.entities.map((ent) => (
                            <span
                              key={ent.id}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-ink-800 text-ink-200 text-xs font-mono"
                            >
                              {ent.name}
                              {ent.entity_type && (
                                <span className="text-amber-400 not-italic">{ent.entity_type}</span>
                              )}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Entities Tab ──────────────────────────────────────────────────────────────

function EntitiesTab({ entities }: { entities: Entity[] }) {
  if (entities.length === 0) {
    return (
      <p className="text-ink-500 text-sm italic py-8 text-center">No entities yet.</p>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {entities.map((ent) => (
        <div key={ent.id} className="card p-4 flex flex-col gap-2">
          <div className="flex items-start justify-between gap-2">
            <span className="chip-mono text-amber-300 text-xs truncate max-w-[120px]">{ent.ref_id}</span>
            <EntityTypeBadge type={ent.entity_type} />
          </div>
          <p className="font-semibold text-ink-50 text-sm leading-snug">{ent.name}</p>
          {ent.description && (
            <p className="text-ink-400 text-sm line-clamp-3">{ent.description}</p>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Documents Tab ─────────────────────────────────────────────────────────────

function DocumentsTab({ documents }: { documents: Document[] }) {
  if (documents.length === 0) {
    return (
      <p className="text-ink-500 text-sm italic py-8 text-center">No documents ingested yet.</p>
    )
  }

  return (
    <div className="divide-y divide-ink-800">
      {documents.map((doc) => {
        const label = doc.filename ?? doc.source_ref
        const truncated = label.length > 60 ? label.slice(0, 60) + '…' : label
        return (
          <div key={doc.id} className="flex items-center gap-3 py-3">
            {doc.source_type === 'file' ? (
              <span className="shrink-0 px-2 py-0.5 rounded text-xs font-medium bg-amber-400/15 text-amber-300">file</span>
            ) : (
              <span className="shrink-0 px-2 py-0.5 rounded text-xs font-medium bg-blue-400/15 text-blue-300">url</span>
            )}
            <span className="flex-1 text-sm text-ink-100 truncate min-w-0" title={label}>
              {truncated}
            </span>
            {doc.page_count != null && (
              <span className="shrink-0 text-xs text-ink-500">{doc.page_count} pages</span>
            )}
            <span className="shrink-0 text-xs text-ink-500">{relativeTime(doc.created_at)}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Images Tab ────────────────────────────────────────────────────────────────

interface ImagesTabProps {
  images: Image[]
  lightboxIndex: number | null
  onOpenLightbox: (index: number) => void
}

function ImagesTab({ images, onOpenLightbox }: ImagesTabProps) {
  if (images.length === 0) {
    return (
      <p className="text-ink-500 text-sm italic py-8 text-center">No images ingested yet.</p>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3">
      {images.map((img, index) => (
        <div
          key={img.id}
          className="card p-3 flex flex-col gap-2 cursor-pointer"
          onClick={() => onOpenLightbox(index)}
        >
          <div className="w-full aspect-square bg-ink-800 rounded-lg flex items-center justify-center">
            <span className="text-2xl font-bold text-ink-500 uppercase">
              {img.filename.charAt(0)}
            </span>
          </div>
          <p className="text-xs text-ink-200 truncate font-medium" title={img.filename}>{img.filename}</p>
          {img.description && (
            <p className="text-xs text-ink-500 line-clamp-2">{img.description}</p>
          )}
          <p className="text-xs text-ink-600 text-right">{relativeTime(img.created_at)}</p>
        </div>
      ))}
    </div>
  )
}

// ── Queue types ───────────────────────────────────────────────────────────────

type QueueItemStatus = 'pending' | 'uploading' | 'done' | 'error'

interface FileQueueItem {
  id: number
  file: File
  status: QueueItemStatus
  error?: string
  jobId?: string
  jobStatus?: 'pending' | 'running' | 'completed' | 'failed'
}

interface UrlQueueItem {
  id: number
  url: string
  status: QueueItemStatus
  error?: string
  jobId?: string
  jobStatus?: 'pending' | 'running' | 'completed' | 'failed'
}

interface ImageQueueItem {
  id: number
  file: File
  previewUrl: string
  status: QueueItemStatus
  error?: string
  jobId?: string
  jobStatus?: 'pending' | 'running' | 'completed' | 'failed'
}

let _queueId = 0

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// ── Queue item status icons ───────────────────────────────────────────────────

function QueueStatusIcon({ status }: { status: QueueItemStatus }) {
  if (status === 'pending') {
    return (
      <svg className="w-4 h-4 text-ink-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
      </svg>
    )
  }
  if (status === 'uploading') {
    return (
      <svg className="w-4 h-4 text-amber-400 shrink-0 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 12a9 9 0 1 1-9-9" />
      </svg>
    )
  }
  if (status === 'done') {
    return (
      <svg className="w-4 h-4 text-emerald-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    )
  }
  return (
    <svg className="w-4 h-4 text-rose-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function JobStatusBadge({ jobStatus }: { jobStatus: string }) {
  const cls =
    jobStatus === 'completed' ? 'bg-emerald-400/15 text-emerald-300' :
    jobStatus === 'failed'    ? 'bg-rose-400/15 text-rose-300' :
    jobStatus === 'running'   ? 'bg-amber-400/15 text-amber-300 animate-pulse' :
                                'bg-ink-700 text-ink-400'
  return <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${cls}`}>{jobStatus}</span>
}

// ── Ingest Tab ────────────────────────────────────────────────────────────────

function IngestTab({
  topicId,
  onDocumentIngested,
  onImageIngested,
  addToast,
}: {
  topicId: string
  onDocumentIngested: () => void
  onImageIngested: () => void
  addToast: (msg: string, type: 'success' | 'error') => void
}) {
  // File queue
  const [fileQueue, setFileQueue] = useState<FileQueueItem[]>([])
  const [fileRunning, setFileRunning] = useState(false)
  const [docDragOver, setDocDragOver] = useState(false)
  const docInputRef = useRef<HTMLInputElement>(null)

  // URL queue
  const [urlQueue, setUrlQueue] = useState<UrlQueueItem[]>([])
  const [urlInput, setUrlInput] = useState('')
  const [urlRunning, setUrlRunning] = useState(false)
  const [urlInputError, setUrlInputError] = useState<string | null>(null)

  // Image queue
  const [imageQueue, setImageQueue] = useState<ImageQueueItem[]>([])
  const [imageDragOver, setImgDragOver] = useState(false)
  const imgInputRef = useRef<HTMLInputElement>(null)
  const [imageRunning, setImageRunning] = useState(false)

  // Auto-process
  const [autoProcess, setAutoProcess] = useState(true)

  // Revoke all image preview URLs on unmount
  useEffect(() => {
    return () => {
      imageQueue.forEach(i => URL.revokeObjectURL(i.previewUrl))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Auto-process helper ──────────────────────────────────────────────────

  async function runAutoProcess<T extends { id: number; jobId?: string; jobStatus?: string }>(
    itemId: number,
    setter: React.Dispatch<React.SetStateAction<T[]>>
  ) {
    if (!autoProcess) return
    try {
      const job = await api.topics.process(topicId)
      setter(prev => prev.map(i => i.id === itemId ? { ...i, jobId: job.id, jobStatus: job.status } : i))
      const poll = setInterval(async () => {
        try {
          const updated = await api.jobs.get(job.id)
          setter(prev => prev.map(i => i.id === itemId ? { ...i, jobStatus: updated.status } : i))
          if (updated.status === 'completed' || updated.status === 'failed') {
            clearInterval(poll)
          }
        } catch { clearInterval(poll) }
      }, 3000)
    } catch {
      // silent — pipeline failure doesn't block queue
    }
  }

  // ── File queue ───────────────────────────────────────────────────────────

  function addFilesToQueue(files: FileList | File[]) {
    const items: FileQueueItem[] = []
    for (const file of Array.from(files)) {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      if (!DOC_EXTS.has(ext)) {
        addToast(`Skipped ${file.name}: unsupported format`, 'error')
        continue
      }
      if (file.size > MAX_DOC_BYTES) {
        addToast(`Skipped ${file.name}: exceeds 25 MB limit`, 'error')
        continue
      }
      items.push({ id: ++_queueId, file, status: 'pending' })
    }
    if (items.length > 0) setFileQueue(prev => [...prev, ...items])
  }

  async function runFileQueue() {
    if (fileRunning) return
    setFileRunning(true)
    const pending = fileQueue.filter(i => i.status === 'pending')
    for (const item of pending) {
      setFileQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'uploading' } : i))
      try {
        await api.topics.ingestFile(topicId, item.file)
        setFileQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'done' } : i))
        onDocumentIngested()
        runAutoProcess(item.id, setFileQueue)
      } catch (err) {
        setFileQueue(prev => prev.map(i => i.id === item.id
          ? { ...i, status: 'error', error: err instanceof Error ? err.message : 'Upload failed' }
          : i))
      }
    }
    setFileRunning(false)
  }

  // ── URL queue ────────────────────────────────────────────────────────────

  function addUrlToQueue() {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    try {
      const parsed = new URL(trimmed)
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error()
    } catch {
      setUrlInputError('Enter a valid http:// or https:// URL')
      return
    }
    setUrlInputError(null)
    setUrlQueue(prev => [...prev, { id: ++_queueId, url: trimmed, status: 'pending' }])
    setUrlInput('')
  }

  async function runUrlQueue() {
    if (urlRunning) return
    setUrlRunning(true)
    const pending = urlQueue.filter(i => i.status === 'pending')
    for (const item of pending) {
      setUrlQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'uploading' } : i))
      try {
        await api.topics.ingestUrl(topicId, item.url)
        setUrlQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'done' } : i))
        onDocumentIngested()
        runAutoProcess(item.id, setUrlQueue)
      } catch (err) {
        setUrlQueue(prev => prev.map(i => i.id === item.id
          ? { ...i, status: 'error', error: err instanceof Error ? err.message : 'Ingest failed' }
          : i))
      }
    }
    setUrlRunning(false)
  }

  // ── Image queue ──────────────────────────────────────────────────────────

  function addImagesToQueue(files: FileList | File[]) {
    const items: ImageQueueItem[] = []
    for (const file of Array.from(files)) {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      if (!IMG_EXTS.has(ext)) {
        addToast(`Skipped ${file.name}: unsupported format`, 'error')
        continue
      }
      if (file.size > MAX_IMG_BYTES) {
        addToast(`Skipped ${file.name}: exceeds 10 MB limit`, 'error')
        continue
      }
      items.push({ id: ++_queueId, file, previewUrl: URL.createObjectURL(file), status: 'pending' })
    }
    if (items.length > 0) setImageQueue(prev => [...prev, ...items])
  }

  async function runImageQueue() {
    if (imageRunning) return
    setImageRunning(true)
    const pending = imageQueue.filter(i => i.status === 'pending')
    for (const item of pending) {
      setImageQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'uploading' } : i))
      try {
        await api.topics.ingestImage(topicId, item.file)
        setImageQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'done' } : i))
        onImageIngested()
        runAutoProcess(item.id, setImageQueue)
      } catch (err) {
        setImageQueue(prev => prev.map(i => i.id === item.id
          ? { ...i, status: 'error', error: err instanceof Error ? err.message : 'Upload failed' }
          : i))
      }
    }
    setImageRunning(false)
  }

  function removeImageFromQueue(id: number) {
    setImageQueue(prev => {
      const item = prev.find(i => i.id === id)
      if (item) URL.revokeObjectURL(item.previewUrl)
      return prev.filter(i => i.id !== id)
    })
  }

  // ── Render ───────────────────────────────────────────────────────────────

  const filePending = fileQueue.filter(i => i.status === 'pending').length
  const urlPending = urlQueue.filter(i => i.status === 'pending').length
  const imgPending = imageQueue.filter(i => i.status === 'pending').length

  return (
    <div className="space-y-0 divide-y divide-ink-800">

      {/* Auto-process toggle */}
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-ink-800">
        <div>
          <p className="text-sm font-medium text-ink-100">Auto-process after ingest</p>
          <p className="text-xs text-ink-500 mt-0.5">Runs the pipeline automatically after each item is ingested</p>
        </div>
        <button
          onClick={() => setAutoProcess(v => !v)}
          className={[
            'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
            autoProcess ? 'bg-amber-400' : 'bg-ink-700',
          ].join(' ')}
          role="switch"
          aria-checked={autoProcess}
        >
          <span className={[
            'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
            autoProcess ? 'translate-x-6' : 'translate-x-1',
          ].join(' ')} />
        </button>
      </div>

      {/* Section 1 — File queue */}
      <div className="pb-8">
        <p className="label-eyebrow mb-4">Ingest Documents</p>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDocDragOver(true) }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDocDragOver(false) }}
          onDrop={(e) => {
            e.preventDefault()
            setDocDragOver(false)
            addFilesToQueue(e.dataTransfer.files)
          }}
          onClick={() => docInputRef.current?.click()}
          className={[
            'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
            docDragOver ? 'border-amber-400' : 'border-ink-700 hover:border-amber-400/50',
          ].join(' ')}
        >
          <input
            ref={docInputRef}
            type="file"
            accept=".pdf,.md,.csv,.json,.yaml,.yml"
            multiple
            className="hidden"
            onChange={(e) => { if (e.target.files) { addFilesToQueue(e.target.files); e.target.value = '' } }}
          />
          <svg className="w-8 h-8 text-ink-600 mx-auto mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <p className="text-sm text-ink-400">Drop files or click to browse</p>
          <p className="text-xs text-ink-600 mt-1">PDF, MD, CSV, JSON, YAML — multiple allowed</p>
        </div>

        {/* File queue list */}
        {fileQueue.length > 0 && (
          <div className="mt-4 space-y-1">
            {fileQueue.map(item => (
              <div key={item.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-ink-900 text-sm">
                <QueueStatusIcon status={item.status} />
                <span className="flex-1 truncate text-ink-100 min-w-0">{item.file.name}</span>
                <span className="text-xs text-ink-500 shrink-0">{formatBytes(item.file.size)}</span>
                {item.error && <span className="text-xs text-rose-400 shrink-0 max-w-[160px] truncate">{item.error}</span>}
                {item.jobId && item.jobStatus && <JobStatusBadge jobStatus={item.jobStatus} />}
                <button
                  onClick={() => setFileQueue(prev => prev.filter(i => i.id !== item.id))}
                  disabled={item.status === 'uploading'}
                  className="text-ink-600 hover:text-rose-400 disabled:opacity-30 shrink-0 leading-none"
                  aria-label="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* File queue actions */}
        <div className="mt-3 flex items-center gap-3">
          {filePending > 0 && (
            <button
              onClick={runFileQueue}
              disabled={fileRunning}
              className="btn-primary text-sm"
            >
              {fileRunning ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 12a9 9 0 1 1-9-9" />
                  </svg>
                  Ingesting…
                </>
              ) : `Ingest All (${filePending})`}
            </button>
          )}
          {fileQueue.some(i => i.status === 'done' || i.status === 'error') && (
            <button
              onClick={() => setFileQueue(prev => prev.filter(i => i.status !== 'done' && i.status !== 'error'))}
              className="btn-ghost text-xs"
            >
              Clear done
            </button>
          )}
        </div>
      </div>

      {/* Section 2 — URL queue */}
      <div className="py-8">
        <p className="label-eyebrow mb-4">Ingest URLs</p>

        {/* URL input row */}
        <div className="flex gap-2">
          <input
            type="url"
            value={urlInput}
            onChange={(e) => { setUrlInput(e.target.value); setUrlInputError(null) }}
            onKeyDown={(e) => { if (e.key === 'Enter') addUrlToQueue() }}
            placeholder="https://..."
            maxLength={500}
            className="input flex-1"
          />
          <button
            onClick={addUrlToQueue}
            disabled={!urlInput.trim()}
            className="btn-secondary text-sm shrink-0"
          >
            Add to queue
          </button>
        </div>
        {urlInputError && <p className="text-xs text-rose-400 mt-1">{urlInputError}</p>}

        {/* URL queue list */}
        {urlQueue.length > 0 && (
          <div className="mt-4 space-y-1">
            {urlQueue.map(item => (
              <div key={item.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-ink-900 text-sm">
                <QueueStatusIcon status={item.status} />
                <span className="flex-1 truncate text-ink-100 min-w-0 max-w-xs" title={item.url}>{item.url}</span>
                {item.error && <span className="text-xs text-rose-400 shrink-0 max-w-[160px] truncate">{item.error}</span>}
                {item.jobId && item.jobStatus && <JobStatusBadge jobStatus={item.jobStatus} />}
                <button
                  onClick={() => setUrlQueue(prev => prev.filter(i => i.id !== item.id))}
                  disabled={item.status === 'uploading'}
                  className="text-ink-600 hover:text-rose-400 disabled:opacity-30 shrink-0 leading-none"
                  aria-label="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* URL queue actions */}
        <div className="mt-3 flex items-center gap-3">
          {urlPending > 0 && (
            <button
              onClick={runUrlQueue}
              disabled={urlRunning}
              className="btn-primary text-sm"
            >
              {urlRunning ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 12a9 9 0 1 1-9-9" />
                  </svg>
                  Ingesting…
                </>
              ) : `Ingest All (${urlPending})`}
            </button>
          )}
          {urlQueue.some(i => i.status === 'done' || i.status === 'error') && (
            <button
              onClick={() => setUrlQueue(prev => prev.filter(i => i.status !== 'done' && i.status !== 'error'))}
              className="btn-ghost text-xs"
            >
              Clear done
            </button>
          )}
        </div>
      </div>

      {/* Section 3 — Image queue */}
      <div className="pt-8">
        <p className="label-eyebrow mb-4">Upload Images</p>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setImgDragOver(true) }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setImgDragOver(false) }}
          onDrop={(e) => {
            e.preventDefault()
            setImgDragOver(false)
            addImagesToQueue(e.dataTransfer.files)
          }}
          onClick={() => imgInputRef.current?.click()}
          className={[
            'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
            imageDragOver ? 'border-amber-400' : 'border-ink-700 hover:border-amber-400/50',
          ].join(' ')}
        >
          <input
            ref={imgInputRef}
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.gif"
            multiple
            className="hidden"
            onChange={(e) => { if (e.target.files) { addImagesToQueue(e.target.files); e.target.value = '' } }}
          />
          <svg className="w-8 h-8 text-ink-600 mx-auto mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
          <p className="text-sm text-ink-400">Drop images or click to browse</p>
          <p className="text-xs text-ink-600 mt-1">PNG, JPG, WEBP, GIF — multiple allowed</p>
        </div>

        {/* Image queue list */}
        {imageQueue.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            {imageQueue.map(item => (
              <div key={item.id} className="flex flex-col items-center gap-1.5 p-2 rounded-lg bg-ink-900 w-28">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={item.previewUrl} alt={item.file.name} className="h-12 w-12 object-cover rounded" />
                <span className="text-xs text-ink-200 truncate w-full text-center" title={item.file.name}>{item.file.name}</span>
                <span className="text-xs text-ink-500">{formatBytes(item.file.size)}</span>
                <div className="flex items-center gap-1">
                  <QueueStatusIcon status={item.status} />
                  {item.jobId && item.jobStatus && <JobStatusBadge jobStatus={item.jobStatus} />}
                </div>
                {item.error && <span className="text-xs text-rose-400 text-center">{item.error}</span>}
                <button
                  onClick={() => removeImageFromQueue(item.id)}
                  disabled={item.status === 'uploading'}
                  className="text-ink-600 hover:text-rose-400 disabled:opacity-30 text-xs leading-none"
                  aria-label="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Image queue actions */}
        <div className="mt-3 flex items-center gap-3">
          {imgPending > 0 && (
            <button
              onClick={runImageQueue}
              disabled={imageRunning}
              className="btn-primary text-sm"
            >
              {imageRunning ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 12a9 9 0 1 1-9-9" />
                  </svg>
                  Uploading…
                </>
              ) : `Upload All (${imgPending})`}
            </button>
          )}
          {imageQueue.some(i => i.status === 'done' || i.status === 'error') && (
            <button
              onClick={() => {
                const toRemove = imageQueue.filter(i => i.status === 'done' || i.status === 'error')
                toRemove.forEach(i => URL.revokeObjectURL(i.previewUrl))
                setImageQueue(prev => prev.filter(i => i.status !== 'done' && i.status !== 'error'))
              }}
              className="btn-ghost text-xs"
            >
              Clear done
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Search Tab ────────────────────────────────────────────────────────────────

function SearchTab({
  topicId,
  onOpenImageLightbox,
}: {
  topicId: string
  onOpenImageLightbox: (images: Image[], index: number) => void
}) {
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<SearchResponse | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  async function handleSearch() {
    const trimmed = query.trim()
    if (!trimmed || searching) return
    const reqId = ++requestIdRef.current
    setSearching(true)
    setSearchError(null)
    try {
      const data = await api.topics.search(topicId, trimmed)
      if (reqId !== requestIdRef.current) return
      setResults(data)
    } catch (err) {
      if (reqId !== requestIdRef.current) return
      setSearchError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      if (reqId === requestIdRef.current) setSearching(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Input row */}
      <div className="flex gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
          maxLength={200}
          className="input flex-1"
          placeholder="Search entities and images…"
        />
        <button
          onClick={handleSearch}
          disabled={searching || !query.trim()}
          className="btn-primary shrink-0"
        >
          {searching ? (
            <>
              <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12a9 9 0 1 1-9-9" />
              </svg>
              Searching…
            </>
          ) : 'Search'}
        </button>
      </div>

      {/* States */}
      {results === null && !searchError && (
        <div className="empty">
          <p>Enter a query to search entities and images semantically.</p>
        </div>
      )}

      {searchError && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4">
          <p className="text-sm text-rose-300">{searchError}</p>
        </div>
      )}

      {results !== null && results.entities.length === 0 && results.images.length === 0 && (
        <div className="empty">
          <p>No matches found for &laquo;{query}&raquo;.</p>
        </div>
      )}

      {/* Entity hits */}
      {results !== null && results.entities.length > 0 && (
        <div>
          <p className="label-eyebrow mb-3">Entity Matches ({results.entities.length})</p>
          <div className="flex flex-col gap-2">
            {results.entities.map((hit, i) => (
              <div key={hit.entity.id + i} className="card p-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300">
                    {Math.round(Math.min(hit.score, 1) * 100)}%
                  </span>
                  <span className="font-semibold text-ink-50">{hit.entity.name}</span>
                  <EntityTypeBadge type={hit.entity.entity_type} />
                </div>
                {hit.matched_excerpt && (
                  <p className="text-sm text-ink-300 border-l-2 border-amber-400/40 pl-3 mt-1 line-clamp-3">
                    {hit.matched_excerpt}
                  </p>
                )}
                {hit.entity.description && (
                  <p className="text-xs text-ink-500 mt-1 line-clamp-2">{hit.entity.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Image hits */}
      {results !== null && results.images.length > 0 && (
        <div>
          <p className="label-eyebrow mb-3">Image Matches ({results.images.length})</p>
          <div className="flex flex-wrap gap-3">
            {results.images.map((hit, i) => (
              <div
                key={hit.image.id + i}
                className="card-hover cursor-pointer w-40 p-3 flex flex-col gap-2"
                onClick={() => onOpenImageLightbox([hit.image], 0)}
              >
                <div className="w-full aspect-square bg-ink-800 rounded-lg flex items-center justify-center">
                  <span className="text-2xl font-bold text-ink-500 uppercase">
                    {hit.image.filename.charAt(0)}
                  </span>
                </div>
                <p className="text-xs text-ink-200 truncate font-medium" title={hit.image.filename}>
                  {hit.image.filename}
                </p>
                <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300 self-start">
                  {Math.round(Math.min(hit.score, 1) * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Tab = 'index' | 'entities' | 'documents' | 'images' | 'ingest' | 'search'

export default function TopicDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [topicId, setTopicId] = useState<string | null>(null)
  const [topic, setTopic] = useState<Topic | null>(null)
  const [subtopics, setSubtopics] = useState<SubTopic[]>([])
  const [topicIndex, setTopicIndex] = useState<TopicIndex | null>(null)
  const [entities, setEntities] = useState<Entity[]>([])
  const [documents, setDocuments] = useState<Document[] | null>(null)
  const [images, setImages] = useState<Image[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeSubtopicId, setActiveSubtopicId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('index')
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [lightboxImages, setLightboxImages] = useState<Image[] | null>(null)
  const [loadError, setLoadError] = React.useState<string | null>(null)
  const [processing, setProcessing] = useState(false)
  const { toasts, addToast } = useToasts()
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollCountRef = React.useRef(0)
  const mountedRef = React.useRef(true)
  const runningRef = React.useRef(false)

  // Resolve async params (Next.js 15)
  useEffect(() => {
    params.then((p) => setTopicId(p.id))
  }, [params])

  const loadAll = useCallback(async (id: string, subtopicFilter?: string | null) => {
    setLoading(true)
    setLoadError(null)
    try {
      const [topicData, subtopicsData, indexData, entitiesData] = await Promise.all([
        api.topics.get(id),
        api.topics.subtopics(id),
        api.topics.index(id),
        api.topics.entities(id, subtopicFilter ?? undefined),
      ])
      setTopic(topicData)
      setSubtopics(subtopicsData)
      setTopicIndex(indexData)
      setEntities(entitiesData)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load topic')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (topicId) loadAll(topicId, null)
  }, [topicId, loadAll])

  // Refetch entities when active subtopic changes
  useEffect(() => {
    if (!topicId) return
    let cancelled = false
    api.topics.entities(topicId, activeSubtopicId ?? undefined)
      .then((d) => { if (!cancelled) setEntities(d) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [topicId, activeSubtopicId])

  // Lazy-load documents when tab is activated
  useEffect(() => {
    if (activeTab !== 'documents' || !topicId || documents !== null) return
    let cancelled = false
    api.topics.documents(topicId)
      .then((d) => { if (!cancelled) setDocuments(d) })
      .catch(() => { if (!cancelled) setDocuments([]) })
    return () => { cancelled = true }
  }, [activeTab, topicId, documents])

  // Lazy-load images when tab is activated
  useEffect(() => {
    if (activeTab !== 'images' || !topicId || images !== null) return
    let cancelled = false
    api.topics.images(topicId)
      .then((d) => { if (!cancelled) setImages(d) })
      .catch(() => { if (!cancelled) setImages([]) })
    return () => { cancelled = true }
  }, [activeTab, topicId, images])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      mountedRef.current = false
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [])

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  const handleRunPipeline = async () => {
    if (!topicId || runningRef.current) return
    runningRef.current = true
    setProcessing(true)
    try {
      const job = await api.topics.process(topicId)
      if (!mountedRef.current) { runningRef.current = false; return }
      pollCountRef.current = 0
      pollingRef.current = setInterval(async () => {
        pollCountRef.current += 1
        if (pollCountRef.current > 200) {
          stopPolling()
          setProcessing(false)
          runningRef.current = false
          addToast('Pipeline timed out — check status later', 'error')
          return
        }
        try {
          const updated = await api.jobs.get(job.id)
          if (!mountedRef.current) return
          if (updated.status === 'completed') {
            stopPolling()
            setProcessing(false)
            runningRef.current = false
            addToast('Pipeline completed', 'success')
            loadAll(topicId, activeSubtopicId)
          } else if (updated.status === 'failed') {
            stopPolling()
            setProcessing(false)
            runningRef.current = false
            addToast(updated.error ?? 'Pipeline failed', 'error')
          }
        } catch {
          if (!mountedRef.current) return
          stopPolling()
          setProcessing(false)
          runningRef.current = false
          addToast('Failed to poll job status', 'error')
        }
      }, 3000)
    } catch (err) {
      setProcessing(false)
      runningRef.current = false
      addToast(err instanceof Error ? err.message : 'Failed to start pipeline', 'error')
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'index', label: 'Index' },
    { key: 'entities', label: 'Entities' },
    { key: 'documents', label: 'Documents' },
    { key: 'images', label: 'Images' },
    { key: 'ingest', label: 'Ingest' },
    { key: 'search', label: 'Search' },
  ]

  function renderTabContent() {
    if (loading) {
      return (
        <div className="space-y-4">
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-4/5" />
        </div>
      )
    }
    if (loadError) {
      return (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-6 text-center">
          <p className="text-sm text-rose-300 mb-3">{loadError}</p>
          <button className="btn-secondary text-xs" onClick={() => topicId && loadAll(topicId, activeSubtopicId)}>Retry</button>
        </div>
      )
    }
    if (activeTab === 'index') return <IndexTab topicIndex={topicIndex} />
    if (activeTab === 'entities') return <EntitiesTab entities={entities} />
    if (activeTab === 'documents') {
      if (documents === null) {
        return (
          <div className="space-y-3">
            <SkeletonBlock className="h-10 w-full" />
            <SkeletonBlock className="h-10 w-full" />
            <SkeletonBlock className="h-10 w-3/4" />
          </div>
        )
      }
      return <DocumentsTab documents={documents} />
    }
    if (activeTab === 'images') {
      if (images === null) {
        return (
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3">
            {[1, 2, 3, 4].map((n) => <SkeletonBlock key={n} className="aspect-square w-full" />)}
          </div>
        )
      }
      return <ImagesTab images={images} lightboxIndex={lightboxIndex} onOpenLightbox={(i) => { setLightboxImages(images); setLightboxIndex(i) }} />
    }
    if (activeTab === 'ingest' && topicId) {
      return (
        <IngestTab
          topicId={topicId}
          onDocumentIngested={() => setDocuments(null)}
          onImageIngested={() => setImages(null)}
          addToast={addToast}
        />
      )
    }
    if (activeTab === 'search' && topicId) {
      return (
        <SearchTab
          key={topicId}
          topicId={topicId}
          onOpenImageLightbox={(imgs, i) => {
            setLightboxImages(imgs)
            setLightboxIndex(i)
          }}
        />
      )
    }
    return null
  }

  return (
    <main className="flex flex-col h-[calc(100vh-57px)]">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4 px-6 lg:px-8 py-4 border-b border-ink-800 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/topics" className="btn-ghost text-xs shrink-0">
            ← Topics
          </Link>
          {loading && !topic ? (
            <SkeletonBlock className="h-5 w-40" />
          ) : (
            <h1 className="font-semibold text-ink-50 truncate">{topic?.name ?? 'Topic'}</h1>
          )}
        </div>
        <button
          onClick={handleRunPipeline}
          disabled={processing || !topicId}
          className="btn-primary shrink-0 min-w-[130px]"
        >
          {processing ? (
            <>
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12a9 9 0 1 1-9-9" />
              </svg>
              Processing…
            </>
          ) : (
            'Run Pipeline'
          )}
        </button>
      </div>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* Subtopics sidebar */}
        <SubtopicsSidebar
          subtopics={subtopics}
          activeId={activeSubtopicId}
          onSelect={setActiveSubtopicId}
        />

        {/* Main content */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Tab bar */}
          <div className="flex items-center gap-1 px-6 border-b border-ink-800 shrink-0">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => { setActiveTab(tab.key); setLightboxIndex(null) }}
                className={[
                  'px-4 py-3 text-sm transition-colors border-b-2',
                  activeTab === tab.key
                    ? 'border-amber-400 text-amber-300 font-medium'
                    : 'border-transparent text-ink-400 hover:text-ink-100',
                ].join(' ')}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto px-6 lg:px-8 py-6">
            {renderTabContent()}
          </div>
        </div>
      </div>

      {lightboxIndex !== null && lightboxImages && (
        <Lightbox
          key={lightboxIndex}
          images={lightboxImages}
          initialIndex={lightboxIndex}
          onClose={() => { setLightboxIndex(null); setLightboxImages(null) }}
        />
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
