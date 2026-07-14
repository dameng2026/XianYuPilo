const TASK_TYPE_LABELS = {
  sync_goods: '同步商品',
  sync_orders: '同步订单'
}

export const DEFAULT_SCHEDULED_TASK_TYPES = [
  'sync_goods',
  'sync_orders'
]

export const SCHEDULER_AVAILABLE = true

export function taskTypeLabel(taskType) {
  const normalized = String(taskType || '').trim().toLowerCase()
  return TASK_TYPE_LABELS[normalized] || normalized || '-'
}

export function normalizeScheduledTaskTypes(taskTypes = DEFAULT_SCHEDULED_TASK_TYPES) {
  return taskTypes.map(value => ({
    value,
    label: taskTypeLabel(value)
  }))
}

export function normalizeScheduledTaskPayload(form) {
  const accountValue = String(form?.accountId ?? '').trim()
  const accountId = Number(accountValue)
  if (!Number.isSafeInteger(accountId) || accountId <= 0) {
    throw new Error('账号 ID 必须是正整数')
  }
  const configValue = String(form?.configJson || '{}').trim() || '{}'
  const config = JSON.parse(configValue)
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    throw new Error('配置 JSON 必须是对象')
  }
  config.accountId = accountId
  return {
    taskName: String(form?.taskName || '').trim(),
    taskType: String(form?.taskType || '').trim().toLowerCase(),
    cronExpression: String(form?.cronExpression || '').trim(),
    configJson: config,
    accountId,
    enabled: form?.enabled ? 1 : 0
  }
}

export function resolveScheduledTaskHeaderAction(eventName, form = {}) {
  const hasTaskId = Number(form?.id) > 0
  const hasTaskName = Boolean(String(form?.taskName || '').trim())

  if (eventName === 'scheduled-task-new') return 'new'
  if (eventName === 'scheduled-task-save') return hasTaskId || hasTaskName ? 'save' : 'focus-name'
  if (eventName === 'scheduled-task-run-current') return hasTaskId ? 'run' : 'select-task'
  return 'ignore'
}
