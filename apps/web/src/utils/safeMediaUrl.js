/**
 * 媒体 URL 安全处理：仅允许可信域名或同源路径的图片资源，
 * 防止 XSS（javascript: 协议）和恶意域名注入。
 */

const MAX_DATA_IMAGE_LENGTH = 2 * 1024 * 1024

const TRUSTED_MEDIA_HOSTS = Object.freeze([
  'alicdn.com',
  'tbcdn.cn',
  'taobaocdn.com',
])

const SAME_ORIGIN_MEDIA_PREFIXES = Object.freeze([
  '/api/',
  '/uploads/',
  '/xya/',
  '/assets/',
])

const ALICDN_MEDIA_PREFIXES = Object.freeze([
  '/bao/uploaded/',
  '/imgextra/',
  '/tfscom/',
])

function activeOrigin() {
  if (typeof window === 'undefined') return 'https://invalid.local'
  return window.location?.origin || 'https://invalid.local'
}

function activeWindow() {
  return typeof window === 'undefined' ? null : window
}

function isTrustedHostname(hostname, trustedHosts) {
  const normalized = String(hostname || '').toLowerCase().replace(/\.$/, '')
  return trustedHosts.some(host => normalized === host || normalized.endsWith(`.${host}`))
}

function isAllowedSameOriginPath(pathname) {
  return SAME_ORIGIN_MEDIA_PREFIXES.some(prefix => pathname.startsWith(prefix))
}

function safeDataImage(value) {
  if (value.length > MAX_DATA_IMAGE_LENGTH) return ''
  return /^data:image\/(?:avif|gif|jpeg|png|webp);base64,[a-z0-9+/=]+$/i.test(value) ? value : ''
}

function relativeUrl(parsed) {
  return `${parsed.pathname}${parsed.search}${parsed.hash}`
}

export function resolveTrustedMediaUrl(value, {
  origin = activeOrigin(),
  trustedHosts = TRUSTED_MEDIA_HOSTS,
} = {}) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (raw.toLowerCase().startsWith('data:')) return safeDataImage(raw)

  let originUrl
  try {
    originUrl = new URL(origin)
  } catch {
    return ''
  }

  if (raw.startsWith('/') && !raw.startsWith('//')) {
    let parsed
    try {
      parsed = new URL(raw, originUrl)
    } catch {
      return ''
    }
    if (parsed.origin !== originUrl.origin || parsed.username || parsed.password) return ''
    if (isAllowedSameOriginPath(parsed.pathname)) return relativeUrl(parsed)
    if (ALICDN_MEDIA_PREFIXES.some(prefix => parsed.pathname.startsWith(prefix))) {
      return `https://img.alicdn.com${relativeUrl(parsed)}`
    }
    return ''
  }

  const candidate = raw.startsWith('//') ? `https:${raw}` : raw
  let parsed
  try {
    parsed = new URL(candidate)
  } catch {
    return ''
  }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return ''
  if (parsed.port && parsed.port !== '443') return ''

  if (parsed.origin === originUrl.origin && isAllowedSameOriginPath(parsed.pathname)) {
    return parsed.href
  }

  const hosts = (Array.isArray(trustedHosts) ? trustedHosts : [])
    .map(host => String(host || '').trim().toLowerCase())
    .filter(Boolean)
  return isTrustedHostname(parsed.hostname, hosts) ? parsed.href : ''
}

export function openTrustedMediaUrl(value, {
  windowLike = activeWindow(),
  trustedHosts = TRUSTED_MEDIA_HOSTS,
} = {}) {
  if (!windowLike?.open) return false
  const safeUrl = resolveTrustedMediaUrl(value, {
    origin: windowLike.location?.origin || activeOrigin(),
    trustedHosts,
  })
  if (!safeUrl) return false
  try {
    const opened = windowLike.open(safeUrl, '_blank', 'noopener,noreferrer')
    if (!opened) return false
    try { opened.opener = null } catch { /* noopener already isolates the window */ }
    return true
  } catch {
    return false
  }
}
