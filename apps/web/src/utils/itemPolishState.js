const TASK_STATUSES = new Set([
  'pending',
  'running',
  'completed',
  'partial',
  'failed',
  'needs_verification',
  'unknown',
])

const RESULT_STATUSES = new Set([
  'pending',
  'in_progress',
  'confirmed',
  'already_done',
  'failed',
  'needs_verification',
  'unknown',
])

const RECONCILE_OUTCOMES = new Set(['confirmed_polished', 'confirmed_not_polished'])
const NEXT_BUSINESS_DAY_RECOVERY = 'retry_next_business_day'
const NEXT_BUSINESS_DAY_TERMINAL_STATUSES = new Set(['partial', 'failed'])
const ISO_TIMESTAMP_WITH_ZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/

export function normalizePolishGoodsIds(goodsIds = []) {
  return [...new Set((goodsIds || []).map(Number).filter(value => Number.isInteger(value) && value > 0))]
    .sort((left, right) => left - right)
}

export function itemPolishScopeKey(accountId, goodsIds = []) {
  const normalizedAccount = Number(accountId || 0)
  const normalizedGoods = normalizePolishGoodsIds(goodsIds)
  return normalizedGoods.length
    ? `account:${normalizedAccount}:goods:${normalizedGoods.join(',')}`
    : `account:${normalizedAccount}:all-active`
}

export function createItemPolishIntent(accountId, goodsIds = []) {
  const normalizedGoods = normalizePolishGoodsIds(goodsIds)
  const random = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return {
    accountId: Number(accountId),
    goodsIds: normalizedGoods,
    idempotencyKey: `item-polish-${random}`,
    taskId: '',
    task: null,
    updatedAt: Date.now(),
  }
}

function countValue(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : fallback
}

function normalizeRetryAfter(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw || !ISO_TIMESTAMP_WITH_ZONE.test(raw)) return null
  const timestamp = Date.parse(raw)
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : null
}

function normalizeResult(value) {
  const status = RESULT_STATUSES.has(String(value?.status)) ? String(value.status) : 'unknown'
  return {
    goodsId: Number(value?.goodsId || 0),
    title: String(value?.title || ''),
    status,
    message: value?.message ? String(value.message) : '',
    errorCode: value?.errorCode ? String(value.errorCode) : '',
    retrySafe: value?.retrySafe === true,
  }
}

export function normalizeItemPolishTask(value, previous = null) {
  const source = value && typeof value === 'object' ? value : {}
  const sourceStatus = String(source.status || '')
  const previousStatus = String(previous?.status || '')
  const status = TASK_STATUSES.has(sourceStatus)
    ? sourceStatus
    : (TASK_STATUSES.has(previousStatus) ? previousStatus : 'unknown')
  const hasResults = Object.prototype.hasOwnProperty.call(source, 'results') && Array.isArray(source.results)
  const previousResults = Array.isArray(previous?.results) ? previous.results : []
  const results = hasResults ? source.results.map(normalizeResult) : previousResults
  const total = countValue(source.total, countValue(previous?.total))
  const processed = countValue(source.processed, countValue(previous?.processed))
  const progress = total === 0 && status === 'completed'
    ? 100
    : Math.min(100, countValue(source.progress, countValue(previous?.progress)))
  return {
    taskId: String(source.taskId || previous?.taskId || ''),
    accountId: Number(source.accountId || previous?.accountId || 0),
    idempotencyKey: String(source.idempotencyKey || previous?.idempotencyKey || ''),
    status,
    running: status === 'running',
    total,
    processed,
    polished: countValue(source.polished, countValue(previous?.polished)),
    alreadyDone: countValue(source.alreadyDone, countValue(previous?.alreadyDone)),
    failed: countValue(source.failed, countValue(previous?.failed)),
    unknown: countValue(source.unknown, countValue(previous?.unknown)),
    progress,
    needManual: status === 'needs_verification',
    message: String(source.message || previous?.message || '擦亮状态暂不可用'),
    retrySafe: Object.prototype.hasOwnProperty.call(source, 'retrySafe')
      ? source.retrySafe === true
      : previous?.retrySafe === true,
    recovery: Object.prototype.hasOwnProperty.call(source, 'recovery')
      ? (source.recovery ? String(source.recovery) : null)
      : (previous?.recovery ? String(previous.recovery) : null),
    retryAfter: Object.prototype.hasOwnProperty.call(source, 'retryAfter')
      ? normalizeRetryAfter(source.retryAfter)
      : normalizeRetryAfter(previous?.retryAfter),
    results,
  }
}

export function itemPolishCanAutoPoll(task) {
  return ['pending', 'running'].includes(String(task?.status || ''))
}

export function itemPolishCanResume(task) {
  if (countValue(task?.unknown) > 0) return false
  if (task?.recovery === NEXT_BUSINESS_DAY_RECOVERY) return false
  return (task?.status === 'pending' && task?.recovery === 'resume_task')
    || (task?.status === 'needs_verification' && task?.retrySafe === true)
    || (['partial', 'failed'].includes(task?.status) && task?.retrySafe === true)
}

function timestampValue(value) {
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'number') return Number.isFinite(value) ? value : Number.NaN
  return typeof value === 'string' && value.trim() ? Date.parse(value) : Number.NaN
}

function retryAfterTimestamp(value) {
  const normalized = normalizeRetryAfter(value)
  return normalized ? Date.parse(normalized) : Number.NaN
}

export function itemPolishCanStartNextBusinessDay(task, now = Date.now()) {
  if (task?.recovery !== NEXT_BUSINESS_DAY_RECOVERY) return false
  if (!NEXT_BUSINESS_DAY_TERMINAL_STATUSES.has(String(task?.status || ''))) return false
  if (countValue(task?.unknown) > 0) return false
  const retryAt = retryAfterTimestamp(task?.retryAfter)
  const current = timestampValue(now)
  return Number.isFinite(retryAt) && Number.isFinite(current) && current >= retryAt
}

export function itemPolishBlocksRetry(task, now = Date.now()) {
  if (task?.status === 'unknown' || countValue(task?.unknown) > 0) return true
  if (task?.recovery === NEXT_BUSINESS_DAY_RECOVERY) {
    return !itemPolishCanStartNextBusinessDay(task, now)
  }
  return false
}

export function itemPolishShouldCreateNewIntent(task, now = Date.now()) {
  return task?.status === 'completed' || itemPolishCanStartNextBusinessDay(task, now)
}

export function itemPolishUnknownResults(task) {
  return (Array.isArray(task?.results) ? task.results : []).filter(result =>
    result?.status === 'unknown' && Number(result?.goodsId) > 0
  )
}

export function createItemPolishReconcilePayload(task, goodsId, outcome) {
  const taskId = String(task?.taskId || '').trim()
  const normalizedGoodsId = Number(goodsId)
  if (!taskId) throw new Error('unknown task is missing taskId')
  if (!RECONCILE_OUTCOMES.has(String(outcome))) throw new Error('unsupported reconcile outcome')
  if (!itemPolishUnknownResults(task).some(result => Number(result.goodsId) === normalizedGoodsId)) {
    throw new Error('selected goods result is not unknown')
  }
  return {
    taskId,
    verifiedInXianyuApp: true,
    items: [{ goodsId: normalizedGoodsId, outcome: String(outcome) }],
  }
}

function retryAfterBusinessTimeText(value) {
  const timestamp = retryAfterTimestamp(value)
  if (!Number.isFinite(timestamp)) return ''
  const businessTime = new Date(timestamp + 8 * 60 * 60 * 1000)
  const part = value => String(value).padStart(2, '0')
  return `${businessTime.getUTCFullYear()}-${part(businessTime.getUTCMonth() + 1)}-${part(businessTime.getUTCDate())} ${part(businessTime.getUTCHours())}:${part(businessTime.getUTCMinutes())}`
}

export function itemPolishRetryGuidance(task, now = Date.now()) {
  if (task?.recovery !== NEXT_BUSINESS_DAY_RECOVERY) return ''
  if (itemPolishCanStartNextBusinessDay(task, now)) {
    return '安全等待期已结束，可新建次日擦亮任务。系统会使用新的幂等键，不会复用旧任务。'
  }
  const retryAfterText = retryAfterBusinessTimeText(task?.retryAfter)
  const availability = retryAfterText
    ? `最早可操作时间：${retryAfterText}（北京时间）。`
    : '服务端尚未提供有效的最早可操作时间，请刷新任务状态。'
  return `为防迟到请求重复操作，本日不再自动重试，次日可新建任务。${availability}`
}

export function itemPolishStatusText(task, now = Date.now()) {
  if (!task) return '擦亮'
  if (task.recovery === NEXT_BUSINESS_DAY_RECOVERY) {
    return itemPolishCanStartNextBusinessDay(task, now)
      ? '新建次日擦亮任务'
      : '本日不再自动重试'
  }
  return {
    pending: itemPolishCanResume(task) ? '继续安全任务' : '等待擦亮',
    running: `擦亮中 ${countValue(task.progress)}%`,
    completed: `已确认 ${countValue(task.polished) + countValue(task.alreadyDone)}/${countValue(task.total)}`,
    partial: task.retrySafe && countValue(task.unknown) === 0 ? '复用原任务处理失败项' : '部分结果待核对',
    failed: task.retrySafe && countValue(task.unknown) === 0 ? '复用原任务重试' : '擦亮失败',
    needs_verification: task.retrySafe ? '验证后继续原任务' : '需完成闲鱼验证',
    unknown: '需在闲鱼 App 核对',
  }[task.status] || '擦亮状态未知'
}

export function classifyItemPolishExistingTask(intent, value) {
  const existingTask = normalizeItemPolishTask(value)
  const sameIntent = Boolean(
    intent?.idempotencyKey
      && existingTask.idempotencyKey
      && intent.idempotencyKey === existingTask.idempotencyKey,
  )
  return {
    status: sameIntent ? 'same_intent' : 'scope_conflict',
    sameIntent,
    existingTask,
    message: sameIntent
      ? existingTask.message
      : `该账号存在另一个商品范围的擦亮任务（${existingTask.taskId || '任务号未知'}）：${existingTask.message}`,
  }
}

export function itemPolishConflictCardState(conflict, now = Date.now()) {
  if (!conflict?.existingTask) return null
  const task = normalizeItemPolishTask(conflict.existingTask)
  const delayedRecovery = task.recovery === NEXT_BUSINESS_DAY_RECOVERY
  const statusLabel = delayedRecovery
    ? (itemPolishCanStartNextBusinessDay(task, now) ? '可新建次日任务' : '本日不再自动重试')
    : ({
    pending: '等待执行',
    running: '执行中',
    completed: '已完成',
    partial: '部分完成',
    failed: '执行失败',
    needs_verification: '需要安全验证',
    unknown: '结果未知',
  }[task.status] || '状态待确认')
  const retryGuidance = itemPolishRetryGuidance(task, now)
  const nextStep = retryGuidance
    ? `${retryGuidance} 请回到既有任务的原任务范围操作；本冲突卡片只提供状态刷新。`
    : ({
    pending: '既有任务正在等待执行；请稍后刷新状态，不要重复提交或改变任务范围。',
    running: '既有任务仍在执行；请等待后刷新状态，不要重复提交或改变任务范围。',
    completed: '既有任务已完成；请核对结果摘要，无需重复提交。',
    partial: '既有任务部分完成；请在原任务范围核对逐项结果，未知项不得重试，本卡片不提供整批恢复。',
    failed: task.retrySafe
      ? '任务已明确失败且标记可安全处理；请回到既有任务的原任务范围决定是否继续，本卡片不会盲目恢复。'
      : '任务失败但未确认可安全重试；请先在原任务范围核对，本卡片不会盲目恢复。',
    needs_verification: '请先在闲鱼 App 完成闲鱼验证，再回到既有任务原范围继续原任务；本卡片不会创建新意图。',
    unknown: '任务结果未知；必须先在闲鱼 App 按 taskId 核对，当前继续禁止重试或重新提交。',
  }[task.status] || '状态尚未确认；只可刷新既有任务状态，不要提交新的擦亮请求。')
  return {
    taskId: task.taskId,
    status: task.status,
    statusLabel,
    progressText: `${task.processed}/${task.total}（${task.progress}%）`,
    counts: {
      polished: task.polished,
      alreadyDone: task.alreadyDone,
      failed: task.failed,
      unknown: task.unknown,
    },
    message: task.message,
    results: task.results.slice(0, 8),
    canRefresh: Boolean(task.taskId),
    allowRetry: false,
    safetyNotice: '此卡片只读取既有任务状态，不会改变账号或商品范围，不会生成新幂等键，也不会重新提交擦亮。',
    nextStep,
  }
}

export async function refreshItemPolishConflictState(conflict, readProgress) {
  const taskId = String(conflict?.existingTask?.taskId || '').trim()
  if (!taskId || typeof readProgress !== 'function') {
    return {
      conflict,
      refreshed: false,
      error: '既有任务缺少可读取的 taskId，已保留当前冲突信息。',
    }
  }
  try {
    const response = await readProgress(taskId)
    const payload = response?.data?.data || response?.data || response
    const existingTask = normalizeItemPolishTask(payload, conflict.existingTask)
    return {
      conflict: {
        ...conflict,
        existingTask,
        message: `该账号存在另一个商品范围的擦亮任务（${existingTask.taskId}）：${existingTask.message}`,
      },
      refreshed: true,
      error: '',
    }
  } catch {
    return {
      conflict,
      refreshed: false,
      error: '刷新既有任务失败，已保留上次确认的冲突卡片；不会因此重新提交擦亮。',
    }
  }
}

export function itemPolishResultText(status) {
  return {
    pending: '等待执行',
    in_progress: '平台确认中',
    confirmed: '已确认擦亮',
    already_done: '今日已擦亮',
    failed: '明确未执行',
    needs_verification: '需要安全验证',
    unknown: '结果未知',
  }[status] || '状态未知'
}
