import { globalConfirm } from '../composables/confirmState.js'

/**
 * 显示确认弹窗（异步，返回 Promise<boolean>）
 * @param {{ title?: string, description?: string, confirmText?: string, dangerous?: boolean }} options
 * @returns {Promise<boolean>}
 */
export async function confirmAction({ title = '确认操作', description = '', confirmText = '', dangerous = false } = {}) {
  return globalConfirm.confirm(title, description, confirmText, dangerous)
}

/**
 * 显示通用删除确认弹窗
 * @param {string} name - 删除对象的名称
 * @returns {Promise<boolean>}
 */
export async function confirmDelete(name = '该数据') {
  return confirmAction({
    title: `确认删除${name}？`,
    description: '删除后可能无法恢复，请确认已完成备份或不再需要。'
  })
}