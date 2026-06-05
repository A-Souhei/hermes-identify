export function buildUpstreamUrl(
  entifierBase: string,
  pathSegments: string[],
  search: string,
): string {
  const base = entifierBase.replace(/\/$/, '')
  const path = pathSegments.map(encodeURIComponent).join('/')
  return search ? `${base}/${path}${search}` : `${base}/${path}`
}
