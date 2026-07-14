import request from '../utils/request.js'

export const generateQrLogin = (data = {}) => request.post('/qrlogin/generate', data)
export const getQrLoginStatus = (sessionId, data = {}) => request.post(`/qrlogin/status/${encodeURIComponent(sessionId)}`, data)
export const cleanupQrLogin = () => request.post('/qrlogin/cleanup', {})
