import request from '../utils/request'
import { pageParams } from '../utils/apiData.js'

export function getGoods(params = {}) {
  const p = pageParams(params)
  if (p.xianyuAccountId && !p.accountId) p.accountId = p.xianyuAccountId
  return request({ url: '/goods', method: 'get', params: p })
}

export function getGoodsStats(params = {}) {
  const p = { ...params }
  if (p.xianyuAccountId && !p.accountId) p.accountId = p.xianyuAccountId
  return request({ url: '/goods/stats', method: 'get', params: p })
}

export function createGoods(data) {
  return request({ url: '/goods', method: 'post', data })
}

export function getGoodsDetail(id, params) {
  return request({ url: `/goods/${id}`, method: 'get', params })
}

export function updateGoods(id, data) {
  return request({ url: `/goods/${id}`, method: 'put', data })
}

export function deleteGoods(id) {
  return deleteGoodsLocal(id)
}

export function deleteGoodsLocal(id) {
  return request({ url: `/goods/${id}/local`, method: 'delete' })
}

export function deleteGoodsRemote(id, data = {}) {
  return request({ url: `/goods/${id}/remote`, method: 'delete', data })
}
