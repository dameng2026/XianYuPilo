import request from '../utils/request.js'

const CATEGORIES = ['ai-customer-service', 'message-settings', 'delivery-settings', 'product-op-settings']

/**
 * 读取指定分类的业务配置
 * @param {string} category  ai-customer-service | message-settings | delivery-settings | product-op-settings
 */
export function getBusinessSettings(category, requestConfig = {}) {
  return request.get(`/business-settings/${encodeURIComponent(category)}`, requestConfig)
}

/**
 * 保存指定分类的业务配置
 */
export function saveBusinessSettings(category, data) {
  return request.post(`/business-settings/${encodeURIComponent(category)}`, data)
}

/**
 * 测试 AI 客服回复
 */
export function testAiCustomerService(message) {
  return request.post('/business-settings/ai-customer-service/test', { message })
}

/**
 * 一次性读取所有分类（并发）
 */
export function getAllBusinessSettings() {
  return Promise.all(CATEGORIES.map(c => getBusinessSettings(c).catch(() => null)))
    .then(results => {
      const map = {}
      CATEGORIES.forEach((c, i) => {
        const res = results[i]
        const data = res?.data ?? res
        map[c] = data && typeof data === 'object' ? data : {}
      })
      return map
    })
}

export const BUSINESS_SETTING_CATEGORIES = CATEGORIES

/**
 * 获取 AI 客服配置的默认值（用于"恢复默认"按钮）。
 */
export function getAiCsDefaults() {
  return request.get('/business-settings/ai-customer-service/defaults')
}

/**
 * 上传知识库文件，由 AI 自动提取回复规则。
 * @param {File} file 用户选择的文件（.md/.ppt/.pptx/.xlsx/.xls/.csv）
 */
export function uploadKnowledgeBase(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/business-settings/ai-customer-service/upload-knowledge', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000
  })
}
