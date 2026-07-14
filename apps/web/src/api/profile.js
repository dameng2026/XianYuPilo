import request from '../utils/request.js'

export const getProfileOverview = () => request.get('/profile/overview')
export const changeProfilePassword = data => request.post('/profile/change-password', data)
