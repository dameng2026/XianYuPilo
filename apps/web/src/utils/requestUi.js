export const REQUEST_UI_MODES = Object.freeze({
  FOREGROUND: 'foreground',
  BACKGROUND: 'background',
  SILENT: 'silent',
})

const VALID_UI_MODES = new Set(Object.values(REQUEST_UI_MODES))

export function normalizeRequestUiMode(config = {}) {
  if (VALID_UI_MODES.has(config.uiMode)) return config.uiMode
  if (config.background === true) return REQUEST_UI_MODES.BACKGROUND
  return REQUEST_UI_MODES.FOREGROUND
}

export function shouldTrackGlobalBusy(detail = {}) {
  return !detail.uiMode || detail.uiMode === REQUEST_UI_MODES.FOREGROUND
}

export function requestRouteFromHash(hash = globalThis.location?.hash || '') {
  const withoutPrefix = String(hash).replace(/^#\/?/, '')
  const encodedRoute = withoutPrefix.split(/[?&]/, 1)[0].replace(/\/+$/, '')
  if (!encodedRoute) return ''
  try {
    return decodeURIComponent(encodedRoute)
  } catch {
    return encodedRoute
  }
}

export function createRequestUiContext(config = {}, requestId = '') {
  const sourceRoute = String(config.uiRoute || requestRouteFromHash())
  return {
    uiMode: normalizeRequestUiMode(config),
    sourceRoute,
    owner: String(config.uiOwner || sourceRoute || 'app'),
    requestScope: String(config.uiScope || config.requestScope || requestId || config.url || 'request'),
  }
}

export function requestUiDetail(config = {}, detail = {}) {
  return { ...(config.xyaUiContext || createRequestUiContext(config, detail.requestId)), ...detail }
}

export function createGlobalRequestNotice(detail = {}, currentRoute = '') {
  if (detail.uiMode === REQUEST_UI_MODES.SILENT) return null
  if (detail.sourceRoute && currentRoute && detail.sourceRoute !== currentRoute) return null
  return {
    text: detail.message || '请求失败，请稍后重试',
    type: 'error',
    retry: typeof detail.retry === 'function' ? detail.retry : null,
    sourceRoute: detail.sourceRoute || currentRoute || '',
    owner: detail.owner || detail.sourceRoute || currentRoute || 'app',
    requestScope: detail.requestScope || detail.requestId || detail.url || 'request',
  }
}

export function retainGlobalNoticeForRoute(notice, nextRoute) {
  if (!notice?.requestScope || !notice?.sourceRoute) return notice
  return notice.sourceRoute === nextRoute ? notice : null
}
