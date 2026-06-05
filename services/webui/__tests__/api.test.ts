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
})
