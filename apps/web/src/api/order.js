import request from '../utils/request.js'

export const listOrders = data => request.post('/order/list', data)
