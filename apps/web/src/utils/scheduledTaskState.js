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

// 解析 HH:MM 时间字符串，返回 { hh, mm }
function parseTime(value) {
  const text = String(value || '00:00').trim()
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(text)
  if (!match) return { hh: '0', mm: '0' }
  const hh = Math.max(0, Math.min(23, Number(match[1]) || 0))
  const mm = Math.max(0, Math.min(59, Number(match[2]) || 0))
  return { hh: String(hh), mm: String(mm) }
}

// 解析 cron 表达式，尝试提取每日 HH:MM 时间
// 仅识别 "0 MM HH * * ?" 或 "0 MM HH * * *" 形式，其他返回 '00:00'
export function cronToDailyTime(cronExpression) {
  const expr = String(cronExpression || '').trim()
  const parts = expr.split(/\s+/)
  if (parts.length < 5) return '00:00'
  const [sec, min, hour] = parts
  // 仅当秒=0、分/时为单值（不含 * / , -）时识别
  if (sec !== '0') return '00:00'
  if (!/^\d{1,2}$/.test(min) || !/^\d{1,2}$/.test(hour)) return '00:00'
  const mm = String(Math.max(0, Math.min(59, Number(min)))).padStart(2, '0')
  const hh = String(Math.max(0, Math.min(23, Number(hour)))).padStart(2, '0')
  return `${hh}:${mm}`
}

// 根据任务类型与配置生成 cron 表达式
// 开源版仅支持 sync_goods / sync_orders，统一使用"每日 HH:MM"模式
export function buildCronExpression(taskType, config = {}) {
  const type = String(taskType || '').toLowerCase()
  // 开源版只支持每日时间模式，其他类型回退到默认 30 分钟间隔
  if (type === 'sync_goods' || type === 'sync_orders') {
    const { hh, mm } = parseTime(config.dailyTime)
    return `0 ${mm} ${hh} * * ?`
  }
  // 兜底：每 30 分钟一次
  return '0 */30 * * * ?'
}

// 从后端任务数据还原表单字段（用于编辑时回填）
// 保留开源版原有的 accountId/cronExpression/configJson 字段，
// 同时新增 dailyTime 字段，由 cron 表达式自动推导
export function hydrateFormFromTask(task) {
  const cronExpression = task?.cronExpression || ''
  const configValue = task?.configJson
  let config = {}
  if (typeof configValue === 'string') {
    try {
      const parsed = JSON.parse(configValue)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) config = parsed
    } catch {
      config = {}
    }
  } else if (configValue && typeof configValue === 'object') {
    config = { ...configValue }
  }

  const accountIdValue = config.accountId ?? config.account_id ?? task?.accountId
  return {
    id: task?.id ?? null,
    taskName: task?.taskName || '',
    taskType: String(task?.taskType || 'sync_goods').toLowerCase(),
    accountId: accountIdValue == null ? '' : String(accountIdValue),
    cronExpression,
    configJson:
      typeof configValue === 'string'
        ? configValue
        : JSON.stringify(config, null, 2),
    dailyTime: cronToDailyTime(cronExpression),
    enabled: task?.enabled === 1 || task?.enabled === true,
  }
}

// 工作流任务类型在开源版不支持，保留函数兼容商业版调用约定
export function taskRequiresAccounts(taskType) {
  return true
}
