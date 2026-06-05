import { NextRequest, NextResponse } from 'next/server'
import { buildUpstreamUrl } from '@/lib/proxy'

const ENTIFIER = (process.env.ENTIFIER_URL ?? 'http://localhost:37491').replace(/\/$/, '')

type Ctx = { params: Promise<{ path: string[] }> }

async function handler(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const { path } = await ctx.params
  const upstream = buildUpstreamUrl(ENTIFIER, path, req.nextUrl.search)

  // Only forward a safe subset of request headers upstream
  const forwardHeaders = new Headers()
  for (const key of ['content-type', 'accept', 'accept-language'] as const) {
    const val = req.headers.get(key)
    if (val !== null) forwardHeaders.set(key, val)
  }

  const body =
    req.method !== 'GET' && req.method !== 'HEAD'
      ? await req.arrayBuffer()
      : undefined

  try {
    const res = await fetch(upstream, {
      method: req.method,
      headers: forwardHeaders,
      body,
    })

    // For any non-ok upstream response, return a generic error (never stream the upstream body)
    if (!res.ok) {
      return NextResponse.json(
        { error: res.statusText || 'upstream error' },
        { status: res.status },
      )
    }

    // Only forward a safe subset of response headers to the client
    const resHeaders = new Headers()
    for (const key of ['content-type', 'cache-control', 'etag'] as const) {
      const val = res.headers.get(key)
      if (val !== null) resHeaders.set(key, val)
    }

    return new NextResponse(res.body, {
      status: res.status,
      headers: resHeaders,
    })
  } catch {
    return NextResponse.json({ error: 'entifier unreachable' }, { status: 502 })
  }
}

export const GET    = handler
export const POST   = handler
export const PATCH  = handler
export const PUT    = handler
export const DELETE = handler
