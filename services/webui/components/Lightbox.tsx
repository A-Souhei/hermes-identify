'use client'

import React from 'react'
import { Image, api } from '@/lib/api'
import { relativeTime } from '@/lib/format'

interface Props {
  images: Image[]
  initialIndex: number
  onClose: () => void
}

export function Lightbox({ images, initialIndex, onClose }: Props) {
  const [idx, setIdx] = React.useState(initialIndex)
  const [errored, setErrored] = React.useState(false)
  const closeRef = React.useRef<HTMLButtonElement>(null)
  const image = images[idx]

  const prev = () => setIdx((i) => Math.max(0, i - 1))
  const next = () => setIdx((i) => Math.min(images.length - 1, i + 1))

  React.useEffect(() => { setErrored(false) }, [idx])

  React.useEffect(() => {
    const previously = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    return () => { previously?.focus() }
  }, [])

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { onClose(); return }
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!image) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Image viewer"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative flex flex-col items-center max-w-4xl w-full mx-4 max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          ref={closeRef}
          onClick={onClose}
          className="absolute -top-10 right-0 text-ink-400 hover:text-ink-50 transition-colors"
          aria-label="Close"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>

        {errored ? (
          <div className="flex items-center justify-center h-48 w-full rounded-lg bg-ink-900 text-ink-500 text-sm">
            Failed to load image
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={api.images.contentUrl(image.id)}
            alt={image.filename}
            onError={() => setErrored(true)}
            className="max-h-[70vh] max-w-full object-contain rounded-lg shadow-2xl"
          />
        )}

        <div className="mt-4 text-center px-4">
          <p className="text-ink-50 font-medium truncate">{image.filename}</p>
          {image.description && (
            <p className="text-ink-400 text-sm mt-1 line-clamp-2">{image.description}</p>
          )}
          <p className="text-ink-600 text-xs mt-1">{relativeTime(image.created_at)}</p>
        </div>

        <p className="text-ink-500 text-xs mt-2">{idx + 1} / {images.length}</p>
      </div>

      {idx > 0 && (
        <button
          onClick={(e) => { e.stopPropagation(); prev() }}
          className="fixed left-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-ink-900/80 text-ink-200 hover:text-ink-50 hover:bg-ink-800 transition-colors"
          aria-label="Previous image"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
      )}

      {idx < images.length - 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); next() }}
          className="fixed right-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-ink-900/80 text-ink-200 hover:text-ink-50 hover:bg-ink-800 transition-colors"
          aria-label="Next image"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      )}
    </div>
  )
}
