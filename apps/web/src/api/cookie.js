/**
 * 账号 Cookie / 登录态兼容 API 模块
 *
 * 说明：
 * - 兼容方法统一转发到当前主账号接口或 WebSocket 兼容接口
 * - 账号登录态以统一认证状态为准，不再直接依赖旧 cookie_status 推断
 */

import request from '../utils/request.js'

/**
 * 更新账号 Cookie（手动输入）
 * 对应后端 POST /api/xianyu/accounts/{id}/cookie
 *
 * @param {number} accountId - 闲鱼账号 ID
 * @param {string} cookieText - 原始 Cookie 字符串
 * @param {object} [extracted] - 前端预提取的字段（可选，后端也会重新提取）
 * @param {string} [extracted.unb] - 提取的 unb
 * @param {string} [extracted.mH5Tk] - 提取的 _m_h5_tk
 * @returns {Promise}
 */
export function updateCookie(accountId, cookieText, extracted) {
  return request({
    url: `/xianyu/accounts/${accountId}/cookie`,
    method: 'post',
    data: {
      cookie: cookieText,
      extractedUnb: extracted?.unb || null,
      extractedMH5Tk: extracted?.mH5Tk || null,
    },
  })
}

/**
 * 手动触发 Cookie 刷新（调用 hasLogin 保活）
 * 对应后端 POST /api/websocket/refreshCookie
 *
 * @param {number} accountId - 闲鱼账号 ID
 * @returns {Promise}
 */
export function refreshCookie(accountId) {
  return request({
    url: '/websocket/refreshCookie',
    method: 'post',
    data: { accountId },
  })
}

/**
 * 检查账号登录状态
 * 对应后端 POST /api/websocket/checkLogin
 *
 * @param {number} accountId - 闲鱼账号 ID
 * @returns {Promise}
 */
export function checkCookieLogin(accountId) {
  return request({
    url: '/websocket/checkLogin',
    method: 'post',
    data: { accountId },
  })
}

/**
 * 获取账号登录状态信息
 * 当前通过统一登录校验接口返回最新状态
 *
 * @param {number} accountId - 闲鱼账号 ID
 * @returns {Promise}
 */
export function getCookieStatus(accountId) {
  return request({
    url: '/websocket/checkLogin',
    method: 'post',
    data: { accountId },
  })
}

// ========== 兼容现有 API 的封装 ==========

/**
 * 通过手动输入 Cookie 创建账号
 * 对应 POST /xianyu/accounts/manual-cookie
 *
 * @param {object} data - { accountNote, cookie, [extractedFields] }
 * @returns {Promise}
 */
export function createAccountByCookie(data) {
  return request({
    url: '/xianyu/accounts/manual-cookie',
    method: 'post',
    data,
  })
}

/**
 * 更新账号 Cookie（兼容现有接口）
 * 对应 POST /api/xianyu/accounts/{id}/cookie
 *
 * @param {number} accountId
 * @param {string} cookie
 * @returns {Promise}
 */
export function updateAccountCookieLegacy(accountId, cookie) {
  return request({
    url: `/xianyu/accounts/${accountId}/cookie`,
    method: 'post',
    data: { cookie },
  })
}
