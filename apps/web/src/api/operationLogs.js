import request from '../utils/request.js'
import { pageParams } from '../utils/apiData.js'

export const getOperationLogs = (params = {}) => request.get('/operation-logs', { params: pageParams(params) })

export const exportOperationLogs = (params = {}) => request.get('/operation-logs/export', { params, responseType: 'blob' })
