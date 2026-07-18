import request from '../utils/request'

function buildParams(params, extra = {}) {
  const merged = { ...params, ...extra }
  if (merged.accountId === '' || merged.accountId === 'all' || merged.accountId == null) {
    delete merged.accountId
  }
  return merged
}

export function getDashboardSummary(params) {
  return request({
    url: '/dashboard/summary',
    method: 'get',
    params: buildParams(params)
  })
}

export function getDashboardSalesTrend(params) {
  return request({
    url: '/dashboard/sales-trend',
    method: 'get',
    params: buildParams(params)
  })
}

export function getDashboardOrderMessageTrend(params) {
  return request({
    url: '/dashboard/order-message-trend',
    method: 'get',
    params: buildParams(params)
  })
}

export function getDashboardAccountHealth(params) {
  return request({
    url: '/dashboard/account-health',
    method: 'get',
    params
  })
}

// 向后兼容：DashboardPage.vue 仍使用 getDashboardStats
export const getDashboardStats = getDashboardSummary