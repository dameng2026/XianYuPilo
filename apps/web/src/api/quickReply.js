import request from '../utils/request.js'

// 快捷回复模板 CRUD
export function listQuickReplyTemplates(params = {}) {
  return request({ url: '/quick-reply/templates', method: 'get', params })
}

export function saveQuickReplyTemplate(data) {
  return request({
    url: '/quick-reply/templates',
    method: 'post',
    data
  })
}

export function deleteQuickReplyTemplate(id) {
  return request({ url: `/quick-reply/templates/${id}`, method: 'delete' })
}

// AI 客服设置，读取 user_business_setting 中的 ai-customer-service
export function getAiCsSetting() {
  return request({ url: '/business-settings/ai-customer-service', method: 'get' })
}

export function saveAiCsSetting(data) {
  return request({
    url: '/business-settings/ai-customer-service',
    method: 'post',
    data
  })
}
