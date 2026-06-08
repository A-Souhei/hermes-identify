import { api } from '../lib/api'

const mockFetch = (body: unknown, ok = true, status = 200) => {
  global.fetch = jest.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(String(body)),
    statusText: 'Error',
  } as unknown as Response)
}

describe('api.topics', () => {
  afterEach(() => jest.restoreAllMocks())

  it('list calls GET /api/entifier/topics', async () => {
    mockFetch([{ id: '1', name: 'T', description: null, created_at: '' }])
    const result = await api.topics.list()
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics', expect.objectContaining({}))
    expect(result[0].name).toBe('T')
  })

  it('create calls POST with name in body', async () => {
    mockFetch({ id: '2', name: 'New', description: null, created_at: '' })
    await api.topics.create('New')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[1].method).toBe('POST')
    expect(JSON.parse(call[1].body)).toMatchObject({ name: 'New' })
  })

  it('create includes description when provided', async () => {
    mockFetch({ id: '3', name: 'X', description: 'desc', created_at: '' })
    await api.topics.create('X', 'desc')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(JSON.parse(call[1].body)).toMatchObject({ name: 'X', description: 'desc' })
  })

  it('throws on non-ok response', async () => {
    mockFetch('bad request', false, 422)
    await expect(api.topics.list()).rejects.toThrow('422')
  })

  it('get calls GET /api/entifier/topics/:id', async () => {
    mockFetch({ id: 'abc', name: 'T', description: null, created_at: '' })
    await api.topics.get('abc')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc', expect.objectContaining({}))
  })

  it('subtopics calls GET /api/entifier/topics/:id/subtopics', async () => {
    mockFetch([])
    await api.topics.subtopics('abc')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc/subtopics', expect.objectContaining({}))
  })

  it('entities calls GET /api/entifier/topics/:id/entities without filter', async () => {
    mockFetch([])
    await api.topics.entities('abc')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc/entities', expect.objectContaining({}))
  })

  it('entities includes ?subtopic_id= when subtopicId is provided', async () => {
    mockFetch([])
    await api.topics.entities('abc', 'st-1')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc/entities?subtopic_id=st-1', expect.objectContaining({}))
  })

  it('process calls POST /api/entifier/topics/:id/process', async () => {
    mockFetch({ id: 'j1', topic_id: 'abc', type: 'pipeline', status: 'pending', error: null, created_at: '', completed_at: null })
    await api.topics.process('abc')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/process')
    expect(call[1].method).toBe('POST')
  })

  it('index calls GET /api/entifier/topics/:id/index', async () => {
    mockFetch({ topic_id: 'abc', topic_name: 'T', subtopics: [] })
    await api.topics.index('abc')
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/entifier/topics/abc/index',
      expect.objectContaining({})
    )
  })

  it('entities encodes subtopicId with special chars', async () => {
    mockFetch([])
    await api.topics.entities('abc', 'st 1')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/entities?subtopic_id=st%201')
  })

  it('documents calls GET /api/entifier/topics/:id/documents', async () => {
    mockFetch([])
    await api.topics.documents('abc')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc/documents', expect.objectContaining({}))
  })

  it('images calls GET /api/entifier/topics/:id/images', async () => {
    mockFetch([])
    await api.topics.images('abc')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc/images', expect.objectContaining({}))
  })

  it('ingestUrl calls POST /api/entifier/topics/:id/ingest/url with url in body', async () => {
    mockFetch({ id: 'd1', topic_id: 'abc', source_type: 'url', source_ref: 'https://example.com', filename: null, page_count: null, minio_key: null, created_at: '' })
    await api.topics.ingestUrl('abc', 'https://example.com')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/ingest/url')
    expect(call[1].method).toBe('POST')
    expect(JSON.parse(call[1].body)).toMatchObject({ url: 'https://example.com' })
  })

  it('ingestFile calls POST /api/entifier/topics/:id/ingest/file with FormData body', async () => {
    mockFetch({ id: 'd2', topic_id: 'abc', source_type: 'file', source_ref: 'doc.pdf', filename: 'doc.pdf', page_count: null, minio_key: null, created_at: '' })
    const file = new File(['content'], 'doc.pdf', { type: 'application/pdf' })
    await api.topics.ingestFile('abc', file)
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/ingest/file')
    expect(call[1].body).toBeInstanceOf(FormData)
  })

  it('ingestFile appends context to FormData when provided', async () => {
    mockFetch({ id: 'd3', topic_id: 'abc', source_type: 'file', source_ref: 'doc.md', filename: 'doc.md', page_count: null, minio_key: null, context: 'my notes', created_at: '' })
    const file = new File(['# Doc'], 'doc.md', { type: 'text/markdown' })
    await api.topics.ingestFile('abc', file, 'my notes')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    const fd = call[1].body as FormData
    expect(fd.get('context')).toBe('my notes')
  })

  it('ingestUrl includes context in JSON body when provided', async () => {
    mockFetch({ id: 'd4', topic_id: 'abc', source_type: 'url', source_ref: 'https://example.com', filename: null, page_count: null, minio_key: null, context: 'url notes', created_at: '' })
    await api.topics.ingestUrl('abc', 'https://example.com', 'url notes')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(JSON.parse(call[1].body)).toMatchObject({ url: 'https://example.com', context: 'url notes' })
  })

  it('ingestUrl omits context key when not provided', async () => {
    mockFetch({ id: 'd5', topic_id: 'abc', source_type: 'url', source_ref: 'https://example.com', filename: null, page_count: null, minio_key: null, created_at: '' })
    await api.topics.ingestUrl('abc', 'https://example.com')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    const body = JSON.parse(call[1].body)
    expect(body).not.toHaveProperty('context')
  })

  it('ingestImage calls POST /api/entifier/topics/:id/ingest/image with FormData body', async () => {
    mockFetch({ id: 'img1', topic_id: 'abc', filename: 'photo.png', description: null, minio_key: null, created_at: '' })
    const file = new File(['img'], 'photo.png', { type: 'image/png' })
    await api.topics.ingestImage('abc', file)
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/ingest/image')
    expect(call[1].body).toBeInstanceOf(FormData)
  })

  it('ingestImage appends context to FormData when provided', async () => {
    mockFetch({ id: 'img2', topic_id: 'abc', filename: 'photo.png', description: 'AI desc', minio_key: null, created_at: '' })
    const file = new File(['img'], 'photo.png', { type: 'image/png' })
    await api.topics.ingestImage('abc', file, 'image notes')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    const fd = call[1].body as FormData
    expect(fd.get('context')).toBe('image notes')
  })

  it('links calls GET /api/entifier/topics/:id/links', async () => {
    mockFetch([{ id: 'other', name: 'Other', description: null, created_at: '' }])
    await api.topics.links('abc')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc/links', expect.objectContaining({}))
  })

  it('addLink posts linked_topic_id to /api/entifier/topics/:id/links', async () => {
    mockFetch({ id: 'xyz', name: 'Linked', description: null, created_at: '' })
    await api.topics.addLink('abc', 'xyz')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/links')
    expect(call[1].method).toBe('POST')
    expect(JSON.parse(call[1].body)).toMatchObject({ linked_topic_id: 'xyz' })
  })

  it('removeLink calls DELETE /api/entifier/topics/:id/links/:otherId', async () => {
    mockFetch(null)
    await api.topics.removeLink('abc', 'xyz').catch(() => {})
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/links/xyz')
    expect(call[1].method).toBe('DELETE')
  })
  it('search posts query to /api/entifier/topics/:id/search', async () => {
    mockFetch({ entities: [], images: [] })
    await api.topics.search('abc', 'solar energy')
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(call[0]).toBe('/api/entifier/topics/abc/search')
    expect(call[1].method).toBe('POST')
    expect(JSON.parse(call[1].body)).toMatchObject({ query: 'solar energy', limit: 10 })
  })

  it('search uses custom limit when provided', async () => {
    mockFetch({ entities: [], images: [] })
    await api.topics.search('abc', 'wind', 5)
    const call = (global.fetch as jest.Mock).mock.calls[0]
    expect(JSON.parse(call[1].body)).toMatchObject({ query: 'wind', limit: 5 })
  })

  it('activeJob calls GET /api/entifier/topics/:id/active-job', async () => {
    mockFetch({ id: 'j1', topic_id: 'abc', type: 'process', status: 'running', error: null, created_at: '', completed_at: null })
    await api.topics.activeJob('abc')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/topics/abc/active-job', expect.objectContaining({}))
  })

  it('activeJob returns null when no active job', async () => {
    mockFetch(null)
    const result = await api.topics.activeJob('abc')
    expect(result).toBeNull()
  })
})

describe('api.jobs', () => {
  afterEach(() => jest.restoreAllMocks())

  it('get calls GET /api/entifier/jobs/:id', async () => {
    mockFetch({ id: 'j1', topic_id: 'abc', type: 'pipeline', status: 'completed', error: null, created_at: '', completed_at: '' })
    await api.jobs.get('j1')
    expect(global.fetch).toHaveBeenCalledWith('/api/entifier/jobs/j1', expect.objectContaining({}))
  })
})

describe('api.images', () => {
  it('images.contentUrl returns correct URL', () => {
    expect(api.images.contentUrl('img-1')).toBe('/api/entifier/images/img-1/content')
  })
})
