'use client'

import { useRef, useState } from 'react'
import { api, SmartIngestResult } from '@/lib/api'

type FileStatus = 'queued' | 'classifying' | 'done' | 'error'

interface FileEntry {
  file: File
  status: FileStatus
  result: SmartIngestResult | null
  error: string | null
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const ACCEPTED_EXTENSIONS = new Set(['.pdf', '.md'])

function getExtension(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx === -1 ? '' : name.slice(idx).toLowerCase()
}

const STATUS_BADGE: Record<FileStatus, string> = {
  queued: 'bg-ink-700 text-ink-300',
  classifying: 'bg-amber-400/20 text-amber-300 animate-pulse',
  done: 'bg-emerald-500/20 text-emerald-300',
  error: 'bg-rose-500/20 text-rose-300',
}

export default function BulkUploadPage() {
  const MAX_FILES = 20

  const [entries, setEntries] = useState<FileEntry[]>([])
  const [running, setRunning] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [invalidFiles, setInvalidFiles] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const dragCounter = useRef(0)
  const [isDragging, setIsDragging] = useState(false)

  function addFiles(files: File[]) {
    if (running) return
    const invalid: string[] = []
    const valid: FileEntry[] = []
    for (const f of files) {
      if (!ACCEPTED_EXTENSIONS.has(getExtension(f.name))) {
        invalid.push(f.name)
      } else {
        valid.push({ file: f, status: 'queued', result: null, error: null })
      }
    }
    setInvalidFiles(invalid)
    setEntries((prev) => {
      const remaining = Math.max(0, MAX_FILES - prev.length)
      return [...prev, ...valid.slice(0, remaining)]
    })
  }

  function updateEntry(index: number, patch: Partial<FileEntry>) {
    setEntries((prev) => prev.map((e, i) => (i === index ? { ...e, ...patch } : e)))
  }

  async function uploadAll() {
    if (running) return
    setRunning(true)
    const indices = entries
      .map((e, i) => i)
      .filter((i) => entries[i].status === 'queued' || entries[i].status === 'error')

    for (const i of indices) {
      updateEntry(i, { status: 'classifying', error: null })
      try {
        const result = await api.smartIngest.file(entries[i].file)
        updateEntry(i, { status: 'done', result })
      } catch (err) {
        updateEntry(i, {
          status: 'error',
          error: err instanceof Error ? err.message : 'Unknown error',
        })
      }
    }
    setRunning(false)
  }

  function onDragEnter(e: React.DragEvent) {
    e.preventDefault()
    dragCounter.current++
    setIsDragging(true)
  }
  function onDragLeave(e: React.DragEvent) {
    e.preventDefault()
    dragCounter.current--
    if (dragCounter.current === 0) setIsDragging(false)
  }
  function onDragOver(e: React.DragEvent) {
    e.preventDefault()
  }
  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    dragCounter.current = 0
    setIsDragging(false)
    addFiles(Array.from(e.dataTransfer.files))
  }

  const doneEntries = entries.filter((e) => e.status === 'done' && e.result)
  const allDone = entries.length > 0 && entries.every((e) => e.status === 'done' || e.status === 'error')

  const uniqueTopicIds = [...new Set(doneEntries.map((e) => e.result!.topic_id))]
  const newTopicsCount = doneEntries.filter((e) => e.result!.was_created).length

  async function processTopics() {
    if (processing) return
    setProcessing(true)
    for (const topicId of uniqueTopicIds) {
      try {
        await api.topics.process(topicId)
      } catch {
        // best-effort per topic
      }
    }
    setProcessing(false)
  }

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink-50">Bulk Upload</h1>
        <p className="text-ink-400 mt-1 text-sm">
          Drop files and we&apos;ll classify them into topics automatically.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={[
          'border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors select-none',
          isDragging
            ? 'border-amber-400 bg-amber-400/5'
            : 'border-ink-700 hover:border-ink-500 hover:bg-ink-800/40',
        ].join(' ')}
      >
        <svg className="w-10 h-10 mx-auto mb-3 text-ink-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <p className="text-ink-300 font-medium">Drop PDF or MD files here</p>
        <p className="text-ink-500 text-sm mt-1">or click to browse</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.md"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(Array.from(e.target.files))
            e.target.value = ''
          }}
        />
      </div>

      {/* Invalid file warning */}
      {invalidFiles.length > 0 && (
        <div className="mt-3 px-4 py-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm">
          Skipped (unsupported type): {invalidFiles.join(', ')}
        </div>
      )}

      {/* File list */}
      {entries.length > 0 && (
        <div className="mt-6 space-y-2">
          {entries.map((entry, i) => (
            <div
              key={`${entry.file.name}-${i}`}
              className="surface border border-ink-700/60 rounded-lg px-4 py-3 flex items-center gap-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-ink-100 text-sm font-medium truncate">{entry.file.name}</p>
                <p className="text-ink-500 text-xs mt-0.5">{formatBytes(entry.file.size)}</p>
                {entry.result && (
                  <p className="text-ink-400 text-xs mt-0.5">
                    Topic:{' '}
                    <span className="text-amber-300 font-medium">{entry.result.topic_name}</span>
                    {entry.result.was_created && (
                      <span className="ml-1 text-emerald-400">(new)</span>
                    )}
                  </p>
                )}
                {entry.error && (
                  <p className="text-rose-400 text-xs mt-0.5 truncate">{entry.error}</p>
                )}
              </div>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${STATUS_BADGE[entry.status]}`}>
                {entry.status}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      {entries.length > 0 && (
        <div className="mt-4 flex gap-3 flex-wrap">
          <button
            onClick={uploadAll}
            disabled={running || entries.every((e) => e.status === 'done')}
            className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {running ? 'Uploading…' : 'Upload All'}
          </button>
          <button
            onClick={() => { setEntries([]); setInvalidFiles([]) }}
            disabled={running}
            className="px-4 py-2 rounded-lg text-sm font-medium text-ink-300 hover:text-ink-100 hover:bg-ink-800/60 transition-colors disabled:opacity-40"
          >
            Clear
          </button>
        </div>
      )}

      {/* Summary */}
      {allDone && doneEntries.length > 0 && (
        <div className="mt-6 surface border border-ink-700/60 rounded-xl p-5">
          <p className="text-ink-100 font-semibold mb-1">Done</p>
          <p className="text-ink-400 text-sm">
            {doneEntries.length} file{doneEntries.length !== 1 ? 's' : ''} ingested across{' '}
            {uniqueTopicIds.length} topic{uniqueTopicIds.length !== 1 ? 's' : ''}.
            {newTopicsCount > 0 && (
              <span className="text-emerald-400 ml-1">{newTopicsCount} new topic{newTopicsCount !== 1 ? 's' : ''} created.</span>
            )}
          </p>
          {uniqueTopicIds.length > 0 && (
            <button
              onClick={processTopics}
              disabled={processing}
              className="mt-3 btn-primary disabled:opacity-50"
            >
              {processing ? 'Processing…' : 'Process all topics'}
            </button>
          )}
        </div>
      )}
    </main>
  )
}
