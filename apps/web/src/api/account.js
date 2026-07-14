import request from '../utils/request.js'

export const listAccounts = () => request.get('/xianyu/accounts', { params: { current: 1, size: 100 } })
export const addAccount = data => request.post('/xianyu/accounts', data)
export const manualAddAccount = data => request.post('/xianyu/accounts/manual-cookie', data)
export const updateAccount = data => request.put(`/xianyu/accounts/${data?.id || data?.accountId}`, data)
export const deleteAccount = accountId => request.delete(`/xianyu/accounts/${accountId}`)
export const getAccountDetail = accountId => request.get(`/xianyu/accounts/${accountId}`)
export const refreshAccountProfile = accountId => request.post(`/xianyu/accounts/${accountId}/refresh-profile`)
