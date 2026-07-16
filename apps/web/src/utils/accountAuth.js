export function accountCookieStatus(account) {
  const status = Number(account?.cookieStatus ?? account?.cookie_status)
  return Number.isNaN(status) ? null : status
}

export function accountLoginCode(account) {
  return account?.loginStatusCode || account?.login_status_code || ''
}

export function accountLoginMessage(account) {
  return account?.loginStatusMessage || account?.login_status_message || ''
}

/**
 * 提取账号 WS 连接状态：优先使用 wsState，其次 account.wsConnected，
 * 最后退回 account.wsStatus 数字字段。返回 true/false/null 三态。
 */
export function accountWsConnectionState(account, wsState) {
  if (wsState && Object.prototype.hasOwnProperty.call(wsState, 'connected')) {
    return typeof wsState.connected === 'boolean' ? wsState.connected : null
  }
  if (account && Object.prototype.hasOwnProperty.call(account, 'wsConnected')) {
    return typeof account.wsConnected === 'boolean' ? account.wsConnected : null
  }
  const rawStatus = account?.wsStatus ?? account?.ws_status
  if (rawStatus === null || rawStatus === undefined || rawStatus === '') return null
  const status = Number(rawStatus)
  return Number.isNaN(status) ? null : status === 1
}

export function accountWsConnected(account, wsState) {
  return accountWsConnectionState(account, wsState) === true
}

/**
 * 开源版原有的三态鉴权判断，保留以兼容现有调用点。
 * 新代码建议改用 resolveAccountAuthDisplayState 以同时感知 WS 状态。
 */
export function accountAuthState(account) {
  if (account?.authConfigured === false || accountLoginCode(account) === 'AUTH_MISSING') return false
  if (account?.authStatusKnown === false || accountLoginCode(account) === 'UNCHECKED') return null
  if (typeof account?.authUsable === 'boolean') return account.authUsable
  const cookieStatus = accountCookieStatus(account)
  const loginCode = accountLoginCode(account)
  if (cookieStatus == null && !loginCode) return null
  if (cookieStatus === 1 && loginCode === 'OK') return true
  if (cookieStatus === 0 || cookieStatus === 2 || loginCode) return false
  return null
}

/**
 * 综合账号 Cookie 预检与 WS 连接状态，输出统一的展示/决策信息。
 * usable=true 表示账号可被选择用于 WS 启动等操作：
 *   Cookie 预检通过 或 WS 当前在线均算可用。
 */
export function resolveAccountAuthDisplayState(account, wsState = null) {
  const wsConnectionState = accountWsConnectionState(account, wsState)
  const cookieStatus = accountCookieStatus(account)
  const loginStatusCode = accountLoginCode(account)
  const rawUsable = typeof account?.authUsable === 'boolean'
    ? account.authUsable
    : cookieStatus === 1 && loginStatusCode === 'OK'
  const wsConnected = wsConnectionState === true
  const usable = rawUsable || wsConnected
  return {
    usable,
    authKnown: typeof account?.authUsable === 'boolean' || cookieStatus !== null || Boolean(loginStatusCode) || wsConnected,
    wsConnected,
    wsConnectionState,
    // Cookie 状态独立反映真实预检结果，不被 WS 状态覆盖
    cookieStatus,
    loginStatusCode,
    loginStatusMessage: rawUsable
      ? '账号登录状态正常'
      : accountLoginMessage(account),
  }
}

export function accountAuthUsable(account, wsState = null) {
  // 优先用综合状态；无 wsState 时退回开源版原有的 accountAuthState 以保留三态语义
  if (wsState !== null) return resolveAccountAuthDisplayState(account, wsState).usable
  const state = accountAuthState(account)
  return state === true
}

/**
 * 从账号列表中挑选首选账号：
 * 1. 若指定 preferredId 且该账号可用 → 直接返回
 * 2. 否则返回第一个可用账号
 * 3. 若都不可用，退回 preferredId 对应账号或列表首项
 */
export function pickPreferredAccount(accounts, preferredId = null) {
  const list = Array.isArray(accounts) ? accounts : []
  if (!list.length) return null

  const preferredKey = String(preferredId ?? '').trim()
  const preferredAccount = preferredKey
    ? list.find(account => String(account?.id ?? '') === preferredKey) || null
    : null

  if (preferredAccount && accountAuthUsable(preferredAccount)) {
    return preferredAccount
  }

  const firstUsableAccount = list.find(accountAuthUsable) || null
  if (firstUsableAccount) {
    return firstUsableAccount
  }

  return preferredAccount || list[0] || null
}

export function resolveAccountAutoReplyScopeEnabled(globalEnabled, accountScopes, accountId) {
  const key = String(accountId ?? '').trim()
  if (!key || !globalEnabled) return false
  const scopes = accountScopes && typeof accountScopes === 'object' ? accountScopes : {}
  if (!Object.prototype.hasOwnProperty.call(scopes, key)) return true
  return scopes[key] === true
}

export function shouldAttemptAccountWebSocketStart(account, wsState) {
  if (!accountAuthUsable(account, wsState)) return false
  if (typeof wsState?.connected === 'boolean' && wsState.connected) return false
  return true
}

export function accountCookieLabel(account, wsState = null) {
  // 有 wsState 时走综合状态；否则保留开源版原有逻辑
  if (wsState !== null) {
    const { cookieStatus: status, loginStatusCode: code } = resolveAccountAuthDisplayState(account, wsState)
    if (status === null || status === undefined) return '状态未知'
    if (status === 2) return '已过期'
    if (status === 0) {
      if (code === 'VERIFYING') return '验证中'
      if (code === 'COOKIE_UPDATED') return '待校验'
      if (code === 'COOKIE_TOKEN_MISSING') return '缺少令牌'
      if (code === 'AUTH_MISSING') return '未登录'
      if (code === 'CAPTCHA_FAILED') return '滑块失败'
      if (code === 'SESSION_EXPIRED') return '需重新登录'
      return '失效/需验证'
    }
    return '正常'
  }
  const status = accountCookieStatus(account)
  const code = accountLoginCode(account)
  if (code === 'UNCHECKED' || account?.authStatusKnown === false) return '待校验'
  if (status == null && !code) return '状态未知'
  if (status === 2) return '已过期'
  if (status === 0) {
    if (code === 'COOKIE_UPDATED') return '待校验'
    if (code === 'COOKIE_TOKEN_MISSING') return '缺少令牌'
    if (code === 'AUTH_MISSING') return '未登录'
    return '失效/需验证'
  }
  if (status === 1 && code && code !== 'OK') return '状态异常'
  return '正常'
}

export function accountCookieBadgeType(account, wsState = null) {
  if (wsState !== null) {
    const { cookieStatus: status, loginStatusCode: code } = resolveAccountAuthDisplayState(account, wsState)
    if (status === null || status === undefined) return 'gray'
    if (status === 2) return 'orange'
    if (status === 0 && (code === 'COOKIE_UPDATED' || code === 'VERIFYING')) return 'orange'
    if (status === 0) return 'red'
    return 'green'
  }
  const status = accountCookieStatus(account)
  const code = accountLoginCode(account)
  if (code === 'UNCHECKED' || account?.authStatusKnown === false) return 'gray'
  if (status == null && !code) return 'gray'
  if (status === 2) return 'orange'
  if (status === 0 && code === 'COOKIE_UPDATED') return 'orange'
  if (status === 0) return 'red'
  return 'green'
}

export function accountLoginHint(account, wsState = null) {
  if (wsState !== null) {
    const { authKnown, loginStatusMessage, usable } = resolveAccountAuthDisplayState(account, wsState)
    if (!authKnown) return '账号登录状态未知，请刷新后确认'
    return loginStatusMessage || (usable ? '账号登录状态正常' : '请重新登录闲鱼账号')
  }
  const state = accountAuthState(account)
  return accountLoginMessage(account) || (state === true ? '账号登录状态正常' : (state === false ? '请重新登录闲鱼账号' : '登录状态尚未验证'))
}
