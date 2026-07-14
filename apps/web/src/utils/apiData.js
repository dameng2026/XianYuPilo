function payloadOf(input) {
  if (!input) return input
  if (Object.prototype.hasOwnProperty.call(input, 'code') && Object.prototype.hasOwnProperty.call(input, 'data')) {
    return input.data
  }
  return input
}

export function recordsOf(input) {
  const data = payloadOf(input)
  if (!data) return []
  if (Array.isArray(data)) return data
  if (Array.isArray(data.records)) return data.records
  if (Array.isArray(data.list)) return data.list
  if (Array.isArray(data.rows)) return data.rows
  if (Array.isArray(data.items)) return data.items
  if (Array.isArray(data.accounts)) return data.accounts
  if (Array.isArray(data.conversations)) return data.conversations
  if (data.data) return recordsOf(data.data)
  return []
}

export function totalOf(input, fallback = 0) {
  const data = payloadOf(input)
  if (!data) return fallback
  return Number(data.total ?? data.totalCount ?? data.count ?? data.pagination?.total ?? fallback) || 0
}

export function unwrap(input) {
  return payloadOf(input) ?? {}
}

export function pageParams(query = {}) {
  const current = query.current ?? query.page ?? query.pageNum ?? 1
  const size = query.size ?? query.pageSize ?? 20
  const result = { ...query, current, size }
  delete result.page
  delete result.pageNum
  delete result.pageSize
  return result
}

export function statusText(value, type = 'normal') {
  const n = Number(value)
  if (type === 'order') return ({0:'待支付',1:'待发货',2:'已发货',3:'已完成',4:'已关闭'}[n] || String(value ?? '-'))
  if (type === 'delivery') return ({0:'待处理',1:'成功',2:'失败',3:'重试中'}[n] || String(value ?? '-'))
  if (type === 'card') return ({0:'未使用',1:'已锁定',2:'已使用',3:'已作废',4:'异常'}[n] || String(value ?? '-'))
  return ({0:'禁用',1:'启用',2:'待验证',3:'已删除'}[n] || String(value ?? '-'))
}

export function statusBadge(value, type = 'normal') {
  const text = statusText(value, type)
  if (['启用','正常','成功','已发货','已完成','未使用'].includes(text)) return 'green'
  if (['失败','禁用','已关闭','已删除'].includes(text)) return 'red'
  return 'orange'
}

export function dateTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

export function camelizeKeys(input) {
  if (Array.isArray(input)) return input.map(camelizeKeys)
  if (!input || typeof input !== 'object') return input

  const output = {}
  for (const [key, value] of Object.entries(input)) {
    const camelKey = key.replace(/_([a-z])/g, (_, char) => char.toUpperCase())
    output[camelKey] = camelizeKeys(value)
  }
  return output
}
