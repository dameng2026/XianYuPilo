import request from '../utils/request.js'

// 知识库 CRUD
export const listKnowledgeBases = (params, config = {}) => request.get('/rag/knowledge-bases', { ...config, params })
export const createKnowledgeBase = (data) => request.post('/rag/knowledge-bases', data)
export const getKnowledgeBase = (id) => request.get(`/rag/knowledge-bases/${id}`)
export const updateKnowledgeBase = (id, data) => request.put(`/rag/knowledge-bases/${id}`, data)
export const deleteKnowledgeBase = (id) => request.delete(`/rag/knowledge-bases/${id}`)

// 文档管理
export const listDocuments = (kbId, params, config = {}) =>
  request.get(`/rag/knowledge-bases/${kbId}/documents`, { ...config, params })

/**
 * 上传文档：支持文本或文件。
 * - 文本：{ content, fileName }
 * - 文件：FormData（field name = file）
 */
export const uploadDocument = (kbId, data) => {
  if (data instanceof FormData) {
    return request.post(`/rag/knowledge-bases/${kbId}/documents`, data)
  }
  const form = new FormData()
  form.append('content', String(data?.content || ''))
  if (data?.fileName) form.append('file_name', String(data.fileName))
  return request.post(`/rag/knowledge-bases/${kbId}/documents`, form)
}
export const deleteDocument = (kbId, docId) =>
  request.delete(`/rag/knowledge-bases/${kbId}/documents/${docId}`)
export const reindexDocument = (kbId, docId) =>
  request.post(`/rag/knowledge-bases/${kbId}/documents/${docId}/reindex`)
export const listChunks = (kbId, docId) =>
  request.get(`/rag/knowledge-bases/${kbId}/documents/${docId}/chunks`)

// 检索 / 对话
export const searchKnowledge = (kbId, data) =>
  request.post(`/rag/knowledge-bases/${kbId}/search`, data)
export const ragChat = (data) => request.post('/rag/chat', data)
