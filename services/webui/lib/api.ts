export interface Topic {
  id: string
  name: string
  description: string | null
  created_at: string
}

const BASE = '/api/entifier'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  topics: {
    list: () => request<Topic[]>('/topics'),
    create: (name: string, description?: string) =>
      request<Topic>('/topics', {
        method: 'POST',
        body: JSON.stringify({ name, description }),
      }),
  },
}
