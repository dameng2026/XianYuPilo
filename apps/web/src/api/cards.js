import request from '../utils/request.js'
import { pageParams } from '../utils/apiData.js'

// ─── 卡密分组 ───
export function getCards(params = {}, config = {}) {
  return request({ ...config, url: '/cards', method: 'get', params: pageParams(params) })
}

export function createCard(data) {
  return request({ url: '/cards', method: 'post', data })
}

export function updateCard(id, data) {
  return request({ url: `/cards/${id}`, method: 'put', data })
}

export function deleteCard(id) {
  return request({ url: `/cards/${id}`, method: 'delete' })
}

// ─── 卡密明细 ───
export function getCardItems(groupId, params = {}, config = {}) {
  return request({ ...config, url: `/cards/${groupId}/items`, method: 'get', params: pageParams(params) })
}

export function createCardItem(groupId, data) {
  return request({ url: `/cards/${groupId}/items`, method: 'post', data })
}

export function batchCreateCardItems(groupId, data) {
  return request({ url: `/cards/${groupId}/items/batch`, method: 'post', data })
}

export function deleteCardItem(groupId, itemId) {
  return request({ url: `/cards/${groupId}/items/${itemId}`, method: 'delete' })
}

export function resetCardItem(groupId, itemId) {
  return request({ url: `/cards/${groupId}/items/${itemId}/reset`, method: 'post' })
}

export function markCardItemInvalid(groupId, itemId) {
  return request({ url: `/cards/${groupId}/items/${itemId}/invalid`, method: 'post' })
}

export function lockCardItem(groupId, itemId) {
  return request({ url: `/cards/${groupId}/items/${itemId}/lock`, method: 'post' })
}

// ─── 库存统计 ───
export function getCardStockStats(groupId, config = {}) {
  return request({ ...config, url: `/cards/${groupId}/stats`, method: 'get' })
}

export function getCardGroupDetail(groupId) {
  return request({ url: `/cards/${groupId}`, method: 'get' })
}

// ─── 使用记录 ───
export function getCardUsageRecords(groupId, params = {}, config = {}) {
  return request({ ...config, url: `/cards/${groupId}/usage`, method: 'get', params: pageParams(params) })
}

// ─── 导出 ───
export function exportCardItems(groupId, params = {}) {
  return request({ url: `/cards/${groupId}/export`, method: 'get', params, responseType: 'blob' })
}

// ─── 库存预警 ───
export function getCardAlerts() {
  return request({ url: '/cards/alerts', method: 'get' })
}
