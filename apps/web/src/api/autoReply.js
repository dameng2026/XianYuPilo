import request from '../utils/request'
import { pageParams } from '../utils/apiData.js'

export function getAutoReplyRules(params = {}) {
  return request({ url: '/auto-reply/rules', method: 'get', params: pageParams(params) })
}

export function createAutoReplyRule(data) {
  return request({ url: '/auto-reply/rules', method: 'post', data })
}

export function updateAutoReplyRule(id, data) {
  if (typeof id === 'object') return request({ url: `/auto-reply/rules/${id.id}`, method: 'put', data: id })
  return request({ url: `/auto-reply/rules/${id}`, method: 'put', data })
}

export function deleteAutoReplyRule(id) {
  return request({ url: `/auto-reply/rules/${id}`, method: 'delete' })
}

export function previewAutoReplyRule(data) {
  return request({ url: '/auto-reply/rules/preview', method: 'post', data })
}

