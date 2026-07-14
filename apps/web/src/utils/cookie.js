/**
 * Cookie 解析与处理工具模块
 *
 * 参考后端 AccountIdentityGuard 设计思路，在前端对用户输入的 Cookie 进行：
 * 1. 解析：将 Cookie 字符串解析为 key=value 映射表
 * 2. 提取关键字段：unb（身份标识）、_m_h5_tk（API 签名 Token）等
 * 3. 格式校验：检查 Cookie 基本格式是否合法
 * 4. 脱敏显示：日志/界面展示时隐藏敏感信息
 */

// 闲鱼 Cookie 中的核心字段
export const COOKIE_KEYS = {
  /** 用户身份标识（必填，用于防串号校验） */
  UNB: 'unb',
  /** API 签名 Token（可选，用于后续 API 调用签名） */
  M_H5_TK: '_m_h5_tk',
  /** 用户 ID */
  USER_ID: 'user_id',
  /** 登录 Token */
  COOKIE_LOGIN_TOKEN: '_cookie_login_token_',
  /** Session ID */
  SESSION_ID: 'sessid',
}

/**
 * 将 Cookie 字符串解析为 key-value 映射表
 * 按 ; 分割，提取 key=value 对
 *
 * @param {string} cookieText - 原始 Cookie 字符串
 * @returns {Record<string, string>} key-value 映射表
 */
export function parseCookie(cookieText) {
  if (!cookieText || typeof cookieText !== 'string') return {}

  const map = {}
  const trimmed = cookieText.trim()

  // 按 ; 分割（可能包含空格）
  const parts = trimmed.split(/;\s*/)

  for (const part of parts) {
    const eqIdx = part.indexOf('=')
    if (eqIdx <= 0) continue // 跳过无 key 或空 key 的项

    const key = part.substring(0, eqIdx).trim()
    const value = part.substring(eqIdx + 1)

    // 只保留非空 key 的项
    if (key) {
      map[key] = value
    }
  }

  return map
}

/**
 * 从 Cookie 字符串中提取指定字段的值
 * 参考后端 extractValue 方法
 *
 * @param {string} cookieText - 原始 Cookie 字符串
 * @param {string} key - 要提取的字段名
 * @returns {string|null} 字段值，不存在则返回 null
 */
export function extractValue(cookieText, key) {
  if (!cookieText || !key) return null

  // 使用正则匹配，避免 key 部分匹配（如 unb 匹配到 xxx_unb）
  // 从开头或 ; 后开始匹配
  const regex = new RegExp(`(?:^|;\\s*)${escapeRegex(key)}=([^;]*)`)
  const match = cookieText.match(regex)
  return match ? match[1] : null
}

/**
 * 转义正则特殊字符
 */
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 从 Cookie 中提取 unb（用户身份标识）
 *
 * @param {string} cookieText - 原始 Cookie 字符串
 * @returns {string|null}
 */
export function extractUnb(cookieText) {
  return extractValue(cookieText, COOKIE_KEYS.UNB)
}

/**
 * 从 Cookie 中提取 _m_h5_tk（API 签名 Token）
 *
 * @param {string} cookieText - 原始 Cookie 字符串
 * @returns {string|null}
 */
export function extractMH5Tk(cookieText) {
  return extractValue(cookieText, COOKIE_KEYS.M_H5_TK)
}

/**
 * 从 Cookie 中提取用户 ID
 *
 * @param {string} cookieText - 原始 Cookie 字符串
 * @returns {string|null}
 */
export function extractUserId(cookieText) {
  return extractValue(cookieText, COOKIE_KEYS.USER_ID)
}

/**
 * 从 Cookie 中提取所有关键字段
 *
 * @param {string} cookieText - 原始 Cookie 字符串
 * @returns {{ unb: string|null, mH5Tk: string|null, userId: string|null, loginToken: string|null, sessionId: string|null, parsedCount: number }}
 */
export function extractKeyFields(cookieText) {
  const parsed = parseCookie(cookieText)
  return {
    unb: extractUnb(cookieText),
    mH5Tk: extractMH5Tk(cookieText),
    userId: extractUserId(cookieText),
    loginToken: extractValue(cookieText, COOKIE_KEYS.COOKIE_LOGIN_TOKEN),
    sessionId: extractValue(cookieText, COOKIE_KEYS.SESSION_ID),
    parsedCount: Object.keys(parsed).length,
  }
}

/**
 * Cookie 格式校验结果
 * @typedef {Object} CookieValidation
 * @property {boolean} valid - 是否通过校验
 * @property {string|null} error - 错误信息（通过时为 null）
 * @property {string|null} warning - 警告信息（如缺少推荐字段但非必填）
 */

/**
 * 校验 Cookie 基本格式
 *
 * @param {string} cookieText - 原始 Cookie 字符串
 * @returns {CookieValidation}
 */
export function validateCookie(cookieText) {
  if (!cookieText || typeof cookieText !== 'string') {
    return { valid: false, error: 'Cookie 不能为空', warning: null }
  }

  const trimmed = cookieText.trim()

  if (trimmed.length < 10) {
    return { valid: false, error: 'Cookie 字符串过短，请检查是否完整复制', warning: null }
  }

  // 检查是否包含 key=value 格式
  if (!trimmed.includes('=')) {
    return { valid: false, error: 'Cookie 格式不正确，缺少 key=value 对', warning: null }
  }

  const parsed = parseCookie(trimmed)
  const warnings = []

  // 检查 unb（必填）
  const unb = extractUnb(trimmed)
  if (!unb) {
    return {
      valid: false,
      error: 'Cookie 缺少 unb 字段，无法确认身份。请确保从闲鱼页面完整复制 Cookie',
      warning: null,
    }
  }

  // 检查 _m_h5_tk（推荐但非必填）
  const mH5Tk = extractMH5Tk(trimmed)
  if (!mH5Tk) {
    warnings.push('缺少 _m_h5_tk 字段，可能影响后续 API 调用签名')
  }

  return {
    valid: true,
    error: null,
    warning: warnings.length > 0 ? warnings.join('；') : null,
    parsed: {
      unb,
      mH5Tk,
      fieldCount: Object.keys(parsed).length,
    },
  }
}

/**
 * 脱敏处理：仅显示字段值的前几位，其余用 * 替代
 * 用于日志输出和界面展示，保护敏感信息
 *
 * @param {string} value - 原始值
 * @param {number} showLen - 显示前几位（默认 4）
 * @returns {string} 脱敏后的字符串
 */
export function maskValue(value, showLen = 4) {
  if (!value) return '(空)'
  if (value.length <= showLen) return value + '***'
  return value.slice(0, showLen) + '***'
}

/**
 * 对 Cookie 中关键字段值进行脱敏
 *
 * @param {object} keyFields - extractKeyFields 返回的结果
 * @returns {object} 脱敏后的字段
 */
export function maskKeyFields(keyFields) {
  return {
    unb: maskValue(keyFields.unb, 4),
    mH5Tk: maskValue(keyFields.mH5Tk, 6),
    userId: maskValue(keyFields.userId, 4),
    loginToken: keyFields.loginToken ? '***' : '(空)',
    sessionId: maskValue(keyFields.sessionId, 4),
    parsedCount: keyFields.parsedCount,
  }
}

/**
 * 校验 Cookie 身份是否与当前账号一致（防串号）
 * 参考后端 AccountIdentityGuard.canUseUnb
 *
 * @param {string|null} cookieUnb - Cookie 中提取的 unb
 * @param {object|null} account - 当前账号对象（需包含 unb 字段）
 * @returns {{ valid: boolean, error: string|null, unbChanged: boolean }}
 */
export function checkIdentity(cookieUnb, account) {
  if (!cookieUnb) {
    return { valid: false, error: 'Cookie 缺少 unb，无法确认身份', unbChanged: false }
  }

  if (!account) {
    // 新账号，无现有 unb 可对比，视为通过
    return { valid: true, error: null, unbChanged: false }
  }

  const currentUnb = account.unb || account.externalUid || ''

  if (!currentUnb) {
    // 账号尚未绑定 unb，首次绑定，通过
    return { valid: true, error: null, unbChanged: false }
  }

  if (currentUnb !== cookieUnb) {
    return {
      valid: false,
      error: `Cookie 身份（unb: ${maskValue(cookieUnb)}）与当前账号（unb: ${maskValue(currentUnb)}）不一致，拒绝跨账号更新`,
      unbChanged: true,
    }
  }

  return { valid: true, error: null, unbChanged: false }
}

/**
 * 获取 Cookie 状态描述
 *
 * @param {number|undefined|null} status - cookie_status 值
 * @returns {{ text: string, type: string }}
 */
export function cookieStatusInfo(status) {
  switch (status) {
    case 1:
      return { text: '有效', type: 'green' }
    case 0:
      return { text: '失效', type: 'red' }
    case 2:
      return { text: '已过期', type: 'orange' }
    default:
      return { text: '未知', type: 'gray' }
  }
}