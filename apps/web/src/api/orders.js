import request from '../utils/request'

export function getOrders(params, config = {}) {
  return request({
    ...config,
    url: '/orders',
    method: 'get',
    params
  })
}

export function getOrderDetail(id, params) {
  return request({
    url: `/orders/${id}`,
    method: 'get',
    params
  })
}

export function updateOrder(id, data) {
  return request({
    url: `/orders/${id}`,
    method: 'put',
    data
  })
}

export function manualDeliverOrder(id, data) {
  const payload = {
    deliveryMode: data?.deliveryMode,
    deliveryContent: data?.deliveryContent,
    quantityRequested: data?.quantityRequested,
    idempotencyKey: data?.idempotencyKey
  }
  return request({
    url: `/orders/${id}/manual-delivery`,
    method: 'post',
    data: payload,
    timeout: 60000
  })
}

export function syncOrder(id) {
  return request({
    url: `/orders/${id}/sync`,
    method: 'post'
  })
}

export function syncOrders(data) {
  return request({
    url: '/orders/sync',
    method: 'post',
    data
  })
}
