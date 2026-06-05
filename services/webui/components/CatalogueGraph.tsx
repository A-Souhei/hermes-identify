'use client'

import { useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { api, Topic } from '@/lib/api'

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false })

interface GraphNode {
  id: string
  name: string
  type: 'topic' | 'subtopic'
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

function buildGraph(
  indices: Array<{ topicId: string; subtopics: Array<{ id: string; name: string }> }>,
  linkPairs: Array<[string, string]>,
): GraphData {
  const nodes: GraphNode[] = []
  const links: GraphLink[] = []

  const topicSet = new Set(indices.map(i => i.topicId))

  for (const { topicId, subtopics } of indices) {
    for (const sub of subtopics) {
      nodes.push({ id: sub.id, name: sub.name, type: 'subtopic', val: 3, color: '#78716c' })
      links.push({ source: topicId, target: sub.id, color: '#44403c', width: 1 })
    }
  }

  for (const [a, b] of linkPairs) {
    if (topicSet.has(a) && topicSet.has(b)) {
      links.push({ source: a, target: b, color: '#f59e0b', width: 2 })
    }
  }

  return { nodes, links }
}

export default function CatalogueGraph({ topics }: Props) {
  const router = useRouter()
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver(entries => {
      const entry = entries[0]
      if (entry) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        })
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (topics.length === 0) return

    let cancelled = false

    async function load() {
      setLoading(true)

      // Per-topic catches so a single failing topic doesn't blank the entire graph
      const [indices, linksByTopic] = await Promise.all([
        Promise.all(
          topics.map(t =>
            api.topics.index(t.id)
              .then(idx => ({ topicId: t.id, subtopics: idx.subtopics }))
              .catch(() => ({ topicId: t.id, subtopics: [] }))
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

      // Deduplicate symmetric topic-link edges; use | separator (UUIDs only contain hex + -)
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

      const topicNodes: GraphNode[] = topics.map(t => ({
        id: t.id,
        name: t.name,
        type: 'topic',
        val: 8,
        color: '#f59e0b',
      }))

      const built = buildGraph(indices, linkPairs)
      built.nodes = [...topicNodes, ...built.nodes]

      setGraphData(built)
      setLoading(false)
    }

    load()
    return () => { cancelled = true }
  }, [topics])

  return (
    <div ref={containerRef} className="h-[calc(100vh-200px)] w-full relative">
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
        <ForceGraph2D
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="#0a0908"
          nodeLabel={(node) => escapeHtml((node as unknown as GraphNode).name)}
          nodeVal="val"
          nodeColor="color"
          linkColor="color"
          linkWidth={(link) => {
            const l = link as unknown as GraphLink
            return typeof l.width === 'number' ? l.width : 1
          }}
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const n = node as unknown as GraphNode & { x: number; y: number }
            const isTopic = n.type === 'topic'
            const fontSize = (isTopic ? 13 : 10) / globalScale
            const label = truncate(n.name, isTopic ? 22 : 18)
            // nodeRelSize default is 4; radius ≈ 4 * √val
            const radius = 4 * Math.sqrt(n.val)
            ctx.font = `${isTopic ? 'bold' : 'normal'} ${fontSize}px Sans-Serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            // subtle dark backing so text is legible over edges
            ctx.fillStyle = 'rgba(10,9,8,0.55)'
            const metrics = ctx.measureText(label)
            const pad = 2 / globalScale
            ctx.fillRect(
              n.x - metrics.width / 2 - pad,
              n.y + radius / globalScale + 1 / globalScale - pad,
              metrics.width + pad * 2,
              fontSize + pad * 2,
            )
            ctx.fillStyle = isTopic ? '#fbbf24' : '#a8a29e'
            ctx.fillText(label, n.x, n.y + radius / globalScale + 1 / globalScale)
          }}
          linkCanvasObjectMode={(link) => {
            const l = link as unknown as GraphLink
            return l.width === 2 ? 'after' : undefined
          }}
          linkCanvasObject={(link, ctx, globalScale) => {
            type SimNode = { x: number; y: number }
            const l = link as unknown as GraphLink & { source: SimNode; target: SimNode }
            if (l.width !== 2) return
            const midX = (l.source.x + l.target.x) / 2
            const midY = (l.source.y + l.target.y) / 2
            const fontSize = 9 / globalScale
            ctx.font = `${fontSize}px Sans-Serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillStyle = 'rgba(10,9,8,0.55)'
            const w = ctx.measureText('linked').width
            const pad = 2 / globalScale
            ctx.fillRect(midX - w / 2 - pad, midY - fontSize / 2 - pad, w + pad * 2, fontSize + pad * 2)
            ctx.fillStyle = '#f59e0b'
            ctx.fillText('linked', midX, midY)
          }}
          onNodeClick={(node) => {
            const n = node as unknown as GraphNode
            if (n.type === 'topic') {
              router.push('/topics/' + encodeURIComponent(n.id))
            }
          }}
        />
      )}
    </div>
  )
}
