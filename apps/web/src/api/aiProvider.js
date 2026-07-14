import request from '../utils/request.js'

// 模型配置（对接 /api/model-config）
// 旧函数名保留以兼容现有页面调用，内部改走新端点。
export const listAiProviders = (params) => request.get('/model-config/list', { params })
export const listAiProvidersByType = (type) => request.get('/model-config/list', { params: { scene: type } })
export const saveAiProvider = (data) =>
  data.id ? request.put(`/model-config/${data.id}`, data) : request.post('/model-config', data)
export const deleteAiProvider = (id) => request.delete(`/model-config/${id}`)
export const activateAiProvider = (id) => request.put(`/model-config/${id}`, { status: 1 })
export const testAiProvider = (data) => request.post(`/model-config/${data.id}/test`, data)
export const getAiProviderModels = (data) =>
  request.get('/model-config/list', { params: { scene: data.type } })
export const getAiProviderStatus = () => request.get('/ai-tools/status')
export const suggestCategoryByAi = (data) => request.post('/ai-tools/category-suggest', data)
