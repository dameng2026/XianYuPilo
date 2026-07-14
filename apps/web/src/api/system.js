import request from '../utils/request.js'

export const currentUser = () => request.post('/system/currentUser', {})
export const changePassword = data => request.post('/system/changePassword', data)
export const runtimeConfig = () => request.get('/system/runtime-config')
export const getOpenSourceConfig = () => request.get('/system/open-source-config')
export const saveOpenSourceConfig = data => request.put('/system/open-source-config', data)
export const getRuntimeStatus = () => request.get('/system/runtime-status')
export const getAboutContent = () => request.get('/system/about-content')
