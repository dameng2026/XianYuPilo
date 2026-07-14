import request from '../utils/request.js'

/**
 * 查询商品列表及每个商品的 effective auto_reply 状态。
 * @param {number} [accountId] 账号ID，不传则返回全部账号商品
 */
export function getAutoReplyScopeProducts(accountId, requestConfig = {}) {
  const params = {}
  if (accountId != null) params.accountId = accountId
  return request.get('/auto-reply-scope/products', { ...requestConfig, params })
}

/**
 * 更新单个商品的 auto_reply_enabled。
 * @param {number} itemId 商品ID
 * @param {boolean} enabled 启用状态
 */
export function updateProductAutoReplyScope(itemId, enabled) {
  return request.post('/auto-reply-scope/product', { itemId, enabled })
}

/**
 * 更新账号级 auto_reply 启用状态。
 * @param {number} accountId 账号ID
 * @param {boolean} enabled 启用状态
 */
export function updateAccountAutoReplyScope(accountId, enabled) {
  return request.post('/auto-reply-scope/account', { accountId, enabled })
}

/**
 * 批量更新商品或账号的 auto_reply 状态。
 * @param {Object} body - {itemIds: [], enabled} 或 {accountIds: [], enabled}
 */
export function batchUpdateAutoReplyScope(body) {
  return request.post('/auto-reply-scope/batch', body)
}

/**
 * 查询全局开关和账号级作用域配置。
 * @param {number} [accountId] 账号ID
 */
export function getAutoReplyScopeStatus(accountId, requestConfig = {}) {
  const params = {}
  if (accountId != null) params.accountId = accountId
  return request.get('/auto-reply-scope/status', { ...requestConfig, params })
}
