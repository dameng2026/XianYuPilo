import request from '../utils/request'

export function getDashboardSummary(params) {
  return request({
    url: '/dashboard/summary',
    method: 'get',
    params
  })
}

export function getDashboardSalesTrend(params) {
  return request({
    url: '/dashboard/sales-trend',
    method: 'get',
    params
  })
}

// 向后兼容：DashboardPage.vue 仍使用 getDashboardStats
export const getDashboardStats = getDashboardSummary
