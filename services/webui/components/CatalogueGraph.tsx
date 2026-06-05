'use client'

import { useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import SpriteText from 'three-spritetext'
import { api, Topic, SubTopicIndexItem } from '@/lib/api'

const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), { ssr: false })

const TOPIC_PALETTE = [
  '#3b82f6', '#10b981', '#8b5cf6', '#f43f5e',
  '#06b6d4', '#84cc16', '#f97316', '#e879f9',
]

interface GraphNode {
  id: string
  name: string
  type: 'topic' | 'subtopic' | 'section' | 'entity'
  val: number
  color: string
}

interface GraphLink {
  source: string
  target: string
  color: string
  width: number
}

interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

interface Props {
  topics: Topic[]
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

const SUBTOPIC_COLOR = '#a78bfa'  // violet
const SECTION_COLOR  = '#34d399'  // emerald
const ENTITY_COLOR   = '#94a3b8'  // slate

function buildGraph(
  topics: Topic[],
  topicColors: Record<string, string>,
  indices: Array<{ topicId: string; subtopics: SubTopicIndexItem[] }>,
  linkPairs: Array<[string, string]>,
): GraphData {
  const nodes: GraphNode[] = []
  const links: GraphLink[] = []
  const topicSet = new Set(topics.map(t => t.id))

  for (const t of topics) {
    nodes.push({ id: t.id, name: t.name, type: 'topic', val: 8, color: topicColors[t.id] })
  }

  for (const { topicId, subtopics } of indices) {
    const topicColor = topicColors[topicId] || '#78716c'

    for (const sub of subtopics) {
      nodes.push({ id: sub.id, name: sub.name, type: 'subtopic', val: 3, color: SUBTOPIC_COLOR })
      links.push({ source: topicId, target: sub.id, color: topicColor, width: 0.3 })

      for (const section of sub.sections) {
        nodes.push({ id: section.id, name: section.name, type: 'section', val: 2, color: SECTION_COLOR })
        links.push({ source: sub.id, target: section.id, color: SUBTOPIC_COLOR, width: 0.2 })

        for (const entity of section.entities) {
          nodes.push({ id: entity.id, name: entity.name, type: 'entity', val: 1, color: ENTITY_COLOR })
          links.push({ source: section.id, target: entity.id, color: SECTION_COLOR, width: 0.15 })
        }
      }
    }
  }

  // Topic-topic links: each colored with the source topic's color
  for (const [a, b] of linkPairs) {
    if (topicSet.has(a) && topicSet.has(b)) {
      links.push({ source: a, target: b, color: topicColors[a] || '#ffffff', width: 0.6 })
    }
  }

  return { nodes, links }
}

export default function CatalogueGraph({ topics }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(topics.length > 0)

  useEffect(() => {
    if (!graphRef.current || !graphData) return
    graphRef.current.d3Force('charge')?.strength(-120)
    graphRef.current.d3Force('link')?.distance(40)
    graphRef.current.d3ReheatSimulation?.()
  }, [graphData])

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver(entries => {
      const entry = entries[0]
      if (entry) setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (topics.length === 0) return
    let cancelled = false

    async function load() {
      setLoading(true)

      const topicColors = Object.fromEntries(
        topics.map((t, i) => [t.id, TOPIC_PALETTE[i % TOPIC_PALETTE.length]])
      )

      const [indices, linksByTopic] = await Promise.all([
        Promise.all(
          topics.map(t =>
            api.topics.index(t.id)
              .then(idx => ({ topicId: t.id, subtopics: idx.subtopics }))
              .catch(() => ({ topicId: t.id, subtopics: [] as SubTopicIndexItem[] }))
          )
        ),
        Promise.all(
          topics.map(t =>
            api.topics.links(t.id)
              .then(linked => linked.map(l => l.id))
              .catch(() => [] as string[])
          )
        ),
      ])

      if (cancelled) return

      const seenEdges = new Set<string>()
      const linkPairs: Array<[string, string]> = []
      for (let i = 0; i < topics.length; i++) {
        const fromId = topics[i].id
        for (const toId of linksByTopic[i]) {
          const key = [fromId, toId].sort().join('|')
          if (!seenEdges.has(key)) {
            seenEdges.add(key)
            linkPairs.push([fromId, toId])
          }
        }
      }

      setGraphData(buildGraph(topics, topicColors, indices, linkPairs))
      setLoading(false)
    }

    load()
    return () => { cancelled = true }
  }, [topics])

  const handleFit    = () => graphRef.current?.zoomToFit(600, 50)
  const handleCenter = () => graphRef.current?.zoomToFit(800, 50)

  return (
    <div ref={containerRef} className="h-[calc(100vh-200px)] w-full relative overflow-hidden">
      {!loading && graphData && (
        <div className="absolute top-3 right-3 z-10 flex flex-col gap-1">
          {[
            { label: '⊡', title: 'Fit all',   fn: handleFit },
            { label: '⊙', title: 'Re-center', fn: handleCenter },
          ].map(({ label, title, fn }) => (
            <button
              key={title}
              onClick={fn}
              title={title}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-ink-800/80 border border-ink-600/40 text-ink-300 hover:bg-ink-700 hover:text-ink-50 text-sm backdrop-blur-sm transition-colors"
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {!loading && graphData && (
        <p className="absolute bottom-3 left-3 z-10 text-[11px] text-ink-600 select-none">
          Drag to orbit · Scroll to zoom · Click node to fly there
        </p>
      )}

      {loading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <svg className="w-8 h-8 animate-spin text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 1 1-9-9" />
            </svg>
            <span className="text-sm text-ink-400">Building graph…</span>
          </div>
        </div>
      )}

      {!loading && graphData && (
        <ForceGraph3D
          ref={graphRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="#050403"
          nodeLabel={(node) => escapeHtml((node as unknown as GraphNode).name)}
          nodeVal="val"
          nodeThreeObjectExtend={true}
          nodeThreeObject={(node) => {
            const n = node as unknown as GraphNode
            const isTopic    = n.type === 'topic'
            const isSubtopic = n.type === 'subtopic'
            const isSection  = n.type === 'section'
            const sprite = new SpriteText(truncate(n.name, isTopic ? 20 : isSubtopic ? 18 : isSection ? 16 : 14))
            sprite.color = n.color
            sprite.textHeight = isTopic ? 5 : isSubtopic ? 3.5 : isSection ? 2.5 : 1.8
            sprite.backgroundColor = 'rgba(0,0,0,0.45)'
            sprite.padding = isTopic ? 2 : 1
            sprite.borderRadius = 3
            return sprite
          }}
          linkColor={(link) => (link as unknown as GraphLink).color}
          linkWidth={(link) => (link as unknown as GraphLink).width}
          linkOpacity={0.7}
          onNodeClick={(node) => {
            const n = node as unknown as GraphNode & { x: number; y: number; z: number }
            if (!isFinite(n.x) || !isFinite(n.y) || !isFinite(n.z)) return
            const distance = n.type === 'topic' ? 120 : n.type === 'subtopic' ? 70 : n.type === 'section' ? 45 : 30
            const mag = Math.hypot(n.x, n.y, n.z) || 1
            const ratio = 1 + distance / mag
            graphRef.current?.cameraPosition(
              { x: n.x * ratio, y: n.y * ratio, z: n.z * ratio },
              { x: n.x, y: n.y, z: n.z },
              1500
            )
          }}
        />
      )}
    </div>
  )
}
