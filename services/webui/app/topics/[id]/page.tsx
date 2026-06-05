'use client'

import Link from 'next/link'
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, Document, Entity, Image, SubTopic, TopicIndex, Topic } from '@/lib/api'
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
  const [docFile, setDocFile] = useState<File | null>(null)
  const [docUploading, setDocUploading] = useState(false)
  const [docError, setDocError] = useState<string | null>(null)
  const [docDragOver, setDocDragOver] = useState(false)
  const docInputRef = useRef<HTMLInputElement>(null)

  const [urlValue, setUrlValue] = useState('')
  const [urlUploading, setUrlUploading] = useState(false)
  const [urlError, setUrlError] = useState<string | null>(null)

  const [imgFile, setImgFile] = useState<File | null>(null)
  const [imgUploading, setImgUploading] = useState(false)
  const [imgError, setImgError] = useState<string | null>(null)
  const [imgDragOver, setImgDragOver] = useState(false)
  const imgInputRef = useRef<HTMLInputElement>(null)
  const imgBlobRef = useRef<string | null>(null)
  const [imgPreview, setImgPreview] = useState<string | null>(null)

  useEffect(() => {
    return () => {
      if (imgBlobRef.current) URL.revokeObjectURL(imgBlobRef.current)
    }
  }, [])

  function setImgFileWithPreview(file: File | null) {
    if (imgBlobRef.current) {
      URL.revokeObjectURL(imgBlobRef.current)
      imgBlobRef.current = null
    }
    setImgFile(file)
    if (file) {
      const url = URL.createObjectURL(file)
      imgBlobRef.current = url
      setImgPreview(url)
    } else {
      setImgPreview(null)
    }
  }

  async function handleDocSubmit() {
    if (!docFile) return
    if (docFile.size > MAX_DOC_BYTES) { setDocError('File exceeds 25 MB limit'); return }
    setDocUploading(true)
    setDocError(null)
    try {
      await api.topics.ingestFile(topicId, docFile)
      addToast('Document ingested', 'success')
      setDocFile(null)
      onDocumentIngested()
    } catch (err) {
      setDocError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setDocUploading(false)
    }
  }

  async function handleUrlSubmit() {
    const trimmed = urlValue.trim()
    if (!trimmed) return
    try {
      const parsed = new URL(trimmed)
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error()
    } catch {
      setUrlError('Enter a valid http:// or https:// URL')
      return
    }
    setUrlUploading(true)
    setUrlError(null)
    try {
      await api.topics.ingestUrl(topicId, urlValue.trim())
      addToast('URL ingested', 'success')
      setUrlValue('')
      onDocumentIngested()
    } catch (err) {
      setUrlError(err instanceof Error ? err.message : 'Ingest failed')
    } finally {
      setUrlUploading(false)
    }
  }

  async function handleImgSubmit() {
    if (!imgFile) return
    if (imgFile.size > MAX_IMG_BYTES) { setImgError('File exceeds 10 MB limit'); return }
    setImgUploading(true)
    setImgError(null)
    try {
      await api.topics.ingestImage(topicId, imgFile)
      addToast('Image uploaded', 'success')
      setImgFileWithPreview(null)
      onImageIngested()
    } catch (err) {
      setImgError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setImgUploading(false)
    }
  }

  return (
    <div className="space-y-0 divide-y divide-ink-800">
      {/* Section 1 — File upload */}
      <div className="pb-8">
        <p className="label-eyebrow mb-4">Ingest Document</p>
        <div
          onDragOver={(e) => { e.preventDefault(); setDocDragOver(true) }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDocDragOver(false) }}
          onDrop={(e) => {
            e.preventDefault()
            setDocDragOver(false)
            const file = e.dataTransfer.files[0]
            if (!file) return
            const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
            if (!DOC_EXTS.has(ext)) { setDocError('Unsupported format. Use PDF, MD, CSV, JSON, or YAML.'); return }
            setDocFile(file)
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
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) setDocFile(f) }}
          />
          {docFile ? (
            <p className="text-sm text-ink-100">{docFile.name}</p>
          ) : (
            <>
              <svg className="w-8 h-8 text-ink-600 mx-auto mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <p className="text-sm text-ink-400">Drop a file or click to browse</p>
              <p className="text-xs text-ink-600 mt-1">PDF, MD, CSV, JSON, YAML</p>
            </>
          )}
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={handleDocSubmit}
            disabled={!docFile || docUploading}
            className="btn-primary text-sm"
          >
            {docUploading ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 1 1-9-9" />
                </svg>
                Uploading…
              </>
            ) : 'Upload'}
          </button>
          {docError && <p className="text-xs text-rose-400">{docError}</p>}
        </div>
      </div>

      {/* Section 2 — URL */}
      <div className="py-8">
        <p className="label-eyebrow mb-4">Ingest URL</p>
        <input
          type="url"
          value={urlValue}
          onChange={(e) => setUrlValue(e.target.value)}
          placeholder="https://..."
          maxLength={500}
          className="input w-full"
        />
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={handleUrlSubmit}
            disabled={!urlValue.trim() || urlUploading}
            className="btn-primary text-sm"
          >
            {urlUploading ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 1 1-9-9" />
                </svg>
                Ingesting…
              </>
            ) : 'Ingest'}
          </button>
          {urlError && <p className="text-xs text-rose-400">{urlError}</p>}
        </div>
      </div>

      {/* Section 3 — Image upload */}
      <div className="pt-8">
        <p className="label-eyebrow mb-4">Upload Image</p>
        <div
          onDragOver={(e) => { e.preventDefault(); setImgDragOver(true) }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setImgDragOver(false) }}
          onDrop={(e) => {
            e.preventDefault()
            setImgDragOver(false)
            const file = e.dataTransfer.files[0]
            if (!file) return
            const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
            if (!IMG_EXTS.has(ext)) { setImgError('Unsupported format. Use PNG, JPG, WEBP, or GIF.'); return }
            setImgFileWithPreview(file)
          }}
          onClick={() => imgInputRef.current?.click()}
          className={[
            'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
            imgDragOver ? 'border-amber-400' : 'border-ink-700 hover:border-amber-400/50',
          ].join(' ')}
        >
          <input
            ref={imgInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) setImgFileWithPreview(f) }}
          />
          {imgPreview ? (
            <div className="flex flex-col items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imgPreview} alt="preview" className="h-20 w-20 object-cover rounded" />
              <p className="text-xs text-ink-400">{imgFile?.name}</p>
            </div>
          ) : (
            <>
              <svg className="w-8 h-8 text-ink-600 mx-auto mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <p className="text-sm text-ink-400">Drop an image or click to browse</p>
              <p className="text-xs text-ink-600 mt-1">PNG, JPG, WEBP, GIF</p>
            </>
          )}
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={handleImgSubmit}
            disabled={!imgFile || imgUploading}
            className="btn-primary text-sm"
          >
            {imgUploading ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 1 1-9-9" />
                </svg>
                Uploading…
              </>
            ) : 'Upload'}
          </button>
          {imgError && <p className="text-xs text-rose-400">{imgError}</p>}
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Tab = 'index' | 'entities' | 'documents' | 'images' | 'ingest'

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
      return <ImagesTab images={images} lightboxIndex={lightboxIndex} onOpenLightbox={(i) => setLightboxIndex(i)} />
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

      {lightboxIndex !== null && images && (
        <Lightbox
          images={images}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
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
