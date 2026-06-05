'use client'

import React from 'react'
import { Image } from '@/lib/api'
import { api } from '@/lib/api'
import { relativeTime } from '@/lib/format'

interface Props {
  images: Image[]
  initialIndex: number
  onClose: () => void
}

export function Lightbox({ images, initialIndex, onClose }: Props) {
  const [idx, setIdx] = React.useState(initialIndex)
  const image = images[idx]

  const prev = () => setIdx((i) => Math.max(0, i - 1))
  const next = () => setIdx((i) => Math.min(images.length - 1, i + 1))

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!image) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Content panel — stop propagation so clicking inside doesn't close */}
      <div
        className="relative flex flex-col items-center max-w-4xl w-full mx-4 max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-ink-400 hover:text-ink-50 transition-colors"
          aria-label="Close"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>

        {/* Image */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={api.images.contentUrl(image.id)}
          alt={image.filename}
          className="max-h-[70vh] max-w-full object-contain rounded-lg shadow-2xl"
        />

        {/* Caption */}
        <div className="mt-4 text-center px-4">
          <p className="text-ink-50 font-medium truncate">{image.filename}</p>
          {image.description && (
            <p className="text-ink-400 text-sm mt-1 line-clamp-2">{image.description}</p>
          )}
          <p className="text-ink-600 text-xs mt-1">{relativeTime(image.created_at)}</p>
        </div>

        {/* Counter */}
        <p className="text-ink-500 text-xs mt-2">{idx + 1} / {images.length}</p>
      </div>

      {/* Prev arrow */}
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

      {/* Next arrow */}
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
