import request from '../utils/request.js'

export const listMessages = data => request.post('/msg/list', data)
export const messageContext = (data, requestConfig = {}) => request.post('/msg/context', data, requestConfig)

/**
 * 获取在线会话列表（实时 IM + cursor 真分页）
 * @param {number} xianyuAccountId 闲鱼账号 ID
 * @param {object} options 分页选项
 * @param {number|null} options.cursor 上一页返回的 nextCursor，首页不传
 * @param {number} options.pageSize 每页数量，默认 20
 */
export const onlineConversations = (xianyuAccountId, { cursor, pageSize = 20 } = {}, requestConfig = {}) =>
  request.get('/msg/online/conversations', {
    ...requestConfig,
    params: { xianyuAccountId, cursor, pageSize }
  })

/**
 * 批量查询会话用户头像和昵称
 * @param {number} accountId 闲鱼账号 ID
 * @param {Array<{cid: string, sid?: string}>} queries 查询列表
 */
export const queryUserAvatars = (accountId, queries, requestConfig = {}) =>
  request.post('/msg/avatars', { accountId, queries }, requestConfig)

export const updateConversationStatus = (id, data) => request.patch(`/conversations/${encodeURIComponent(id)}/status`, data)
export const markConversationRead = (id, requestConfig = {}) =>
  request.patch(`/conversations/${encodeURIComponent(id)}/read`, undefined, requestConfig)
