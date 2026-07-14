import request from '../utils/request.js'

export const startWebSocket = (accountId, config = {}) => request.post('/websocket/start', { accountId }, config)
export const stopWebSocket = accountId => request.post('/websocket/stop', { accountId })
export const websocketStatus = (accountId, config = {}) => request.post('/websocket/status', { accountId }, config)
export const sendMessage = data => request.post('/websocket/sendMessage', data)
export const sendImageMessage = data => request.post('/websocket/sendImageMessage', data)
export const updateCookie = data => request.post('/websocket/updateCookie', data)
export const refreshCookie = accountId => request.post('/websocket/refreshCookie', { accountId })
export const retryAutoCaptcha = accountId => request.post('/websocket/retryAutoCaptcha', { accountId })
export const checkLogin = accountId => request.post('/websocket/checkLogin', { accountId })
