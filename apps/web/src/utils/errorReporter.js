import request from './request.js'

const STORAGE_KEY = 'xya_client_error_buffer'
const MAX_BUFFER_SIZE = 30
const MAX_BATCH_SIZE = 20
const MAX_STORAGE_CHARS = 64 * 1024
const MAX_MESSAGE_CHARS = 1200
const MAX_STACK_CHARS = 5000
const MAX_EVENT_AGE_MS = 7 * 24 * 60 * 60 * 1000
const SENSITIVE_KEY = /authorization|cookie|set-cookie|token|password|passwd|secret|api[-_]?key|credential/i
let installed = false
let flushPromise = null
const reporterState = {
  status: 'idle',
  lastAttemptAt: '',
  lastSuccessAt: '',
  lastError: '',
}

function truncate(value, maxLength) {
  const text = String(value || '')
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text
}

function redactUrl(rawUrl) {
  try {
    const url = new URL(rawUrl)
    url.username = ''
    url.password = ''
    if (url.search) url.search = '?[REDACTED]'
    if (url.hash) url.hash = '#[REDACTED]'
    return url.toString()
  } catch {
    return '[REDACTED_URL]'
  }
}

export function sanitizeClientErrorText(value, maxLength = MAX_MESSAGE_CHARS) {
  let text = String(value || '')
  text = text.replace(/https?:\/\/[^\s"'<>]+/gi, match => redactUrl(match))
  text = text.replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, 'Bearer [REDACTED]')
  text = text.replace(/((?:authorization|cookie|set-cookie|token|password|passwd|secret|api[-_]?key|credential)\s*[:=]\s*)[^\s,;"'}]+/gi, '$1[REDACTED]')
  text = text.replace(/("(?:authorization|cookie|set-cookie|token|password|passwd|secret|api[-_]?key|credential)"\s*:\s*")[^"]*(")/gi, '$1[REDACTED]$2')
  return truncate(text, maxLength)
}

function sanitizeContext(input, depth = 0) {
  if (depth > 3 || input == null) return null
  if (typeof input === 'string') return sanitizeClientErrorText(input, 500)
  if (typeof input === 'number' || typeof input === 'boolean') return input
  if (Array.isArray(input)) return input.slice(0, 10).map(item => sanitizeContext(item, depth + 1))
  if (typeof input !== 'object') return sanitizeClientErrorText(String(input), 500)
  const result = {}
  for (const [key, value] of Object.entries(input).slice(0, 20)) {
    result[key] = SENSITIVE_KEY.test(key) ? '[REDACTED]' : sanitizeContext(value, depth + 1)
  }
  return result
}

function sanitizeStoredEvent(item) {
  if (!item || typeof item !== 'object') return null
  return {
    message: sanitizeClientErrorText(item.message, MAX_MESSAGE_CHARS),
    stack: sanitizeClientErrorText(item.stack, MAX_STACK_CHARS),
    type: sanitizeClientErrorText(item.type || 'client_error', 80),
    source: sanitizeClientErrorText(item.source, 240),
    line: Number.isFinite(Number(item.line)) ? Number(item.line) : null,
    column: Number.isFinite(Number(item.column)) ? Number(item.column) : null,
    route: sanitizeClientErrorText(item.route, 300),
    userAgent: sanitizeClientErrorText(item.userAgent, 500),
    time: String(item.time || new Date().toISOString()),
    context: sanitizeContext(item.context),
  }
}

function readBuffer() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    if (!Array.isArray(parsed)) return []
    const cutoff = Date.now() - MAX_EVENT_AGE_MS
    return parsed
      .map(sanitizeStoredEvent)
      .filter(item => item && (!Number.isFinite(Date.parse(item.time)) || Date.parse(item.time) >= cutoff))
      .slice(-MAX_BUFFER_SIZE)
  } catch {
    return []
  }
}

function writeBuffer(items) {
  try {
    const bounded = items.map(sanitizeStoredEvent).filter(Boolean).slice(-MAX_BUFFER_SIZE)
    while (bounded.length && JSON.stringify(bounded).length > MAX_STORAGE_CHARS) bounded.shift()
    localStorage.setItem(STORAGE_KEY, JSON.stringify(bounded))
  } catch {
    // Storage can be unavailable in private mode; reporting must never break the app.
  }
}

function currentRoute() {
  const path = String(location.pathname || '/')
  return path
    .split('/')
    .map(segment => (/^\d+$/.test(segment) || /^[0-9a-f-]{16,}$/i.test(segment) ? ':id' : segment))
    .join('/') || '/'
}

function normalizeError(input, extra = {}) {
  const error = input?.reason || input?.error || input
  return sanitizeStoredEvent({
    message: error?.message || String(error || 'Unknown client error'),
    stack: error?.stack || '',
    type: extra.type || input?.type || 'client_error',
    source: extra.source || input?.filename || '',
    line: input?.lineno || null,
    column: input?.colno || null,
    route: currentRoute(),
    userAgent: '',
    time: new Date().toISOString(),
    context: extra.context || null,
  })
}

export function recordClientError(input, extra = {}) {
  const event = normalizeError(input, extra)
  const buffer = readBuffer()
  buffer.push(event)
  writeBuffer(buffer)
  if (import.meta.env?.DEV) console.warn('[client-error-buffer]', event.type)
  return event
}

async function performFlush() {
  const buffer = readBuffer()
  if (!buffer.length) return { sent: 0, pending: 0 }
  if (navigator.onLine === false) return { sent: 0, pending: buffer.length, offline: true }

  reporterState.status = 'sending'
  reporterState.lastAttemptAt = new Date().toISOString()
  reporterState.lastError = ''
  const batch = buffer.slice(0, MAX_BATCH_SIZE)
  try {
    const res = await request({
      url: '/client-errors',
      method: 'post',
      data: { events: batch },
      uiMode: 'silent',
    })
    const data = res?.data || res || {}
    const accepted = Math.max(0, Number(data.accepted ?? batch.length) || 0)
    const dropped = Math.max(0, Number(data.dropped || 0) || 0)
    const confirmed = Math.min(batch.length, accepted + dropped)
    writeBuffer(buffer.slice(confirmed))
    reporterState.status = 'success'
    reporterState.lastSuccessAt = new Date().toISOString()
    return { sent: accepted, dropped, pending: Math.max(0, buffer.length - confirmed) }
  } catch (error) {
    reporterState.status = 'error'
    reporterState.lastError = sanitizeClientErrorText(error?.message || '上报失败', 300)
    return { sent: 0, pending: buffer.length, error: reporterState.lastError }
  }
}

export function flushClientErrors() {
  if (!flushPromise) flushPromise = performFlush().finally(() => { flushPromise = null })
  return flushPromise
}

export function installClientErrorReporter() {
  if (installed) return
  installed = true
  window.addEventListener('error', event => recordClientError(event, { type: 'window_error' }))
  window.addEventListener('unhandledrejection', event => recordClientError(event, { type: 'unhandled_rejection' }))
  setTimeout(flushClientErrors, 2000)
  window.addEventListener('online', () => flushClientErrors())
}

export function getBufferedClientErrors() {
  return readBuffer()
}

export function getClientErrorReporterState() {
  return { ...reporterState }
}
