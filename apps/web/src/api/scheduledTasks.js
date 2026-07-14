import request from '../utils/request.js'
import { pageParams } from '../utils/apiData.js'

export function getScheduledTasks(params = {}) {
  return request({ url: '/scheduled-tasks', method: 'get', params: pageParams(params) })
}
export function createScheduledTask(data) {
  return request({ url: '/scheduled-tasks', method: 'post', data })
}
export function updateScheduledTask(id, data) {
  return request({ url: `/scheduled-tasks/${id}`, method: 'put', data })
}
export function deleteScheduledTask(id) {
  return request({ url: `/scheduled-tasks/${id}`, method: 'delete' })
}
export function runScheduledTask(id) {
  // The API waits for the real sync outcome (server timeout: 300s) instead of
  // returning a fake "triggered" acknowledgement.
  return request({ url: `/scheduled-tasks/${id}/run`, method: 'post', timeout: 310000 })
}
