import request from '../utils/request'

export function getNavigationOverview(params) {
  return request({
    url: '/navigation/overview',
    method: 'get',
    params
  })
}

export function getNavigationNotifications(params) {
  return request({
    url: '/navigation/notifications',
    method: 'get',
    params
  })
}

export function getNavigationSystemStatus(params) {
  return request({
    url: '/navigation/system-status',
    method: 'get',
    params
  })
}