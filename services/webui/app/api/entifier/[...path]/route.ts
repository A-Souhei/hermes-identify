import { NextRequest, NextResponse } from 'next/server'
import { buildUpstreamUrl } from '@/lib/proxy'

const ENTIFIER = (process.env.ENTIFIER_URL ?? 'http://localhost:37491').replace(/\/$/, '')

type Ctx = { params: Promise<{ path: string[] }> }

async function handler(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const { path } = await ctx.params
  const upstream = buildUpstreamUrl(ENTIFIER, path, req.nextUrl.search)

  const headers = new Headers(req.headers)
  headers.delete('host')

  const body =
    req.method !== 'GET' && req.method !== 'HEAD'
      ? await req.arrayBuffer()
      : undefined

  try {
    const res = await fetch(upstream, {
      method: req.method,
      headers,
      body,
    })

    const resHeaders = new Headers(res.headers)
    resHeaders.delete('content-encoding')

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
