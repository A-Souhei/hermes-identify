import { buildUpstreamUrl } from '../lib/proxy'

describe('buildUpstreamUrl', () => {
  it('joins base and path segments', () => {
    expect(buildUpstreamUrl('http://localhost:37491', ['topics'], ''))
      .toBe('http://localhost:37491/topics')
  })

  it('handles nested path segments', () => {
    expect(buildUpstreamUrl('http://localhost:37491', ['topics', 'abc-123', 'subtopics'], ''))
      .toBe('http://localhost:37491/topics/abc-123/subtopics')
  })

  it('appends search string when present', () => {
    expect(buildUpstreamUrl('http://localhost:37491', ['topics'], '?limit=10'))
      .toBe('http://localhost:37491/topics?limit=10')
  })

  it('strips trailing slash from base', () => {
    expect(buildUpstreamUrl('http://entifier:8000/', ['health'], ''))
      .toBe('http://entifier:8000/health')
  })

  it('encodes special characters in path segments', () => {
    const result = buildUpstreamUrl('http://localhost:37491', ['topics', 'hello world'], '')
    expect(result).toBe('http://localhost:37491/topics/hello%20world')
  })
})
