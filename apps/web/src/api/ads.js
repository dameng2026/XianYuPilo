import request from '../utils/request.js'

const TERMINAL_PAYMENT_STATUSES = new Set(['paid', 'closed', 'failed'])

function paymentStatusRank(status) {
  if (TERMINAL_PAYMENT_STATUSES.has(String(status || '').toLowerCase())) return 2
  if (String(status || '').toLowerCase() === 'pending') return 1
  return 0
}

/**
 * Accept payment observations only for the exact order being inspected and
 * never let a later-arriving, older observation regress an accepted state.
 */
export function reduceAdPaymentOrder(current, incoming, identity = {}) {
  const applicationId = Number(identity.applicationId || 0)
  const orderNo = String(identity.orderNo || '').trim()
  const nextOrderNo = String(incoming?.orderNo || '').trim()
  const nextApplicationId = Number(incoming?.applicationId || incoming?.adApplicationId || 0)

  if (!Number.isInteger(applicationId) || applicationId <= 0 || !orderNo) return current
  if (nextOrderNo !== orderNo) return current
  if (nextApplicationId > 0 && nextApplicationId !== applicationId) return current

  const currentOrderNo = String(current?.orderNo || '').trim()
  if (current && currentOrderNo === orderNo) {
    const currentStatus = String(current.statusKey || '').toLowerCase()
    const nextStatus = String(incoming?.statusKey || '').toLowerCase()
    if (TERMINAL_PAYMENT_STATUSES.has(currentStatus)) return current
    if (paymentStatusRank(nextStatus) < paymentStatusRank(currentStatus)) return current
  }

  return incoming
}

export function getTextAds() {
  return request.get('/ads/text', { suppressGlobalError: true })
}

export function getAdPlans() {
  return request.get('/ads/plans', { suppressGlobalError: true })
}

export function listAdApplications(params = {}) {
  return request.get('/ads/applications', { params, suppressGlobalError: true })
}

export function submitAdApplication(data) {
  return request.post('/ads/applications', data)
}

export function getAdPaymentMethods() {
  return request.get('/ads/payment/methods', { suppressGlobalError: true })
}

export function createAdPaymentOrder(applicationId, data = {}) {
  return request.post(`/ads/applications/${applicationId}/payment-order`, data)
}

export function getAdPaymentOrder(orderNo, config = {}) {
  return request.get(`/ads/payment/orders/${orderNo}`, config)
}

export function closeAdPaymentOrder(orderNo) {
  return request.post(`/ads/payment/orders/${orderNo}/close`, {})
}
