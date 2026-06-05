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

export interface SubTopic {
  id: string
  topic_id: string
  name: string
  description: string | null
  keywords: string | null
  created_at: string
}

export interface Entity {
  id: string
  ref_id: string
  topic_id: string
  subtopic_id: string | null
  section_id: string | null
  name: string
  description: string | null
  entity_type: string | null
  created_at: string
}

export interface EntityIndexItem {
  id: string
  ref_id: string
  name: string
  entity_type: string | null
}

export interface SectionIndexItem {
  id: string
  name: string
  description: string | null
  order_index: number
  entities: EntityIndexItem[]
}

export interface SubTopicIndexItem {
  id: string
  name: string
  description: string | null
  sections: SectionIndexItem[]
}

export interface TopicIndex {
  topic_id: string
  topic_name: string
  subtopics: SubTopicIndexItem[]
}

export interface Job {
  id: string
  topic_id: string
  type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  error: string | null
  created_at: string
  completed_at: string | null
}

export const api = {
  topics: {
    list: () => request<Topic[]>('/topics'),
    create: (name: string, description?: string) =>
      request<Topic>('/topics', {
        method: 'POST',
        body: JSON.stringify({ name, description }),
      }),
    get: (id: string) => request<Topic>(`/topics/${encodeURIComponent(id)}`),
    subtopics: (id: string) => request<SubTopic[]>(`/topics/${encodeURIComponent(id)}/subtopics`),
    entities: (id: string, subtopicId?: string) =>
      request<Entity[]>(
        `/topics/${encodeURIComponent(id)}/entities${subtopicId ? `?subtopic_id=${encodeURIComponent(subtopicId)}` : ''}`
      ),
    index: (id: string) => request<TopicIndex>(`/topics/${encodeURIComponent(id)}/index`),
    process: (id: string) => request<Job>(`/topics/${encodeURIComponent(id)}/process`, { method: 'POST' }),
  },
  jobs: {
    get: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
  },
}
