import request from '../utils/request.js'

export const listModules = () => request.get('/modules')
export const getModuleMeta = (key) => request.get(`/modules/${key}/meta`)
