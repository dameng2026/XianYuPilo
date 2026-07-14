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

export function accountAuthUsable(account) {
  return accountAuthState(account) === true
}

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

export function accountCookieLabel(account) {
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

export function accountCookieBadgeType(account) {
  const status = accountCookieStatus(account)
  const code = accountLoginCode(account)
  if (code === 'UNCHECKED' || account?.authStatusKnown === false) return 'gray'
  if (status == null && !code) return 'gray'
  if (status === 2) return 'orange'
  if (status === 0 && code === 'COOKIE_UPDATED') return 'orange'
  if (status === 0) return 'red'
  return 'green'
}

export function accountLoginHint(account) {
  const state = accountAuthState(account)
  return accountLoginMessage(account) || (state === true ? '账号登录状态正常' : (state === false ? '请重新登录闲鱼账号' : '登录状态尚未验证'))
}

export function accountWsConnected(account, wsState) {
  if (typeof wsState?.connected === 'boolean') {
    return wsState.connected
  }
  if (typeof account?.wsConnected === 'boolean') {
    return account.wsConnected
  }
  const rawStatus = account?.wsStatus ?? account?.ws_status
  if (rawStatus == null || rawStatus === '') return null
  const status = Number(rawStatus)
  if (status === 1) return true
  if (status === 0) return false
  return null
}
