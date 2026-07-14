import request from '../utils/request'

function normalizeParams(params = {}) {
  const limit = Number(params.limit || params.size || params.pageSize || 20)
  const offset = Number(params.offset || 0)
  const current = params.current || params.page || Math.floor(offset / Math.max(limit, 1)) + 1
  const result = { ...params, current, size: limit }
  if (result.xianyuAccountId && !result.accountId) result.accountId = result.xianyuAccountId
  delete result.xianyuAccountId
  delete result.limit
  delete result.offset
  delete result.page
  delete result.pageSize
  return result
}

export function getConversations(params = {}, requestConfig = {}) {
  return request({
    ...requestConfig,
    url: '/conversations',
    method: 'get',
    params: normalizeParams(params)
  })
}

