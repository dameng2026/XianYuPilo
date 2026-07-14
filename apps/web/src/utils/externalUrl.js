export function normalizeExternalUrl(value, baseUrl = globalThis.location?.origin || 'http://localhost') {
  const raw = String(value || '').trim()
  if (!raw) return ''
  try {
    const url = new URL(raw, baseUrl)
    if (!['http:', 'https:'].includes(url.protocol)) return ''
    return url.href
  } catch {
    return ''
  }
}

/** Open only HTTP(S) URLs in an isolated browsing context. */
export function openExternalUrl(value) {
  const href = normalizeExternalUrl(value)
  if (!href) return false
  const opened = window.open(href, '_blank', 'noopener,noreferrer')
  if (opened) opened.opener = null
  return true
}
