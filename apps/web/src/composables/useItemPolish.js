import { onScopeDispose, reactive } from 'vue'
import { getItemPolishProgress, reconcileItemPolish, runItemPolish } from '../api/items.js'
import {
  classifyItemPolishExistingTask,
  createItemPolishReconcilePayload,
  createItemPolishIntent,
  itemPolishCanAutoPoll,
  itemPolishBlocksRetry,
  itemPolishRetryGuidance,
  itemPolishShouldCreateNewIntent,
  itemPolishScopeKey,
  normalizeItemPolishTask,
  normalizePolishGoodsIds,
  refreshItemPolishConflictState,
} from '../utils/itemPolishState.js'

const STORAGE_KEY = 'xya:item-polish-intents:v1'
const POLL_INTERVAL_MS = 1200
const MAX_PENDING_POLLS = 8
const MAX_POLL_ERRORS = 3
const MAX_TIMER_DELAY_MS = 2_147_000_000

function availableStorage(explicit) {
  if (explicit) return explicit
  try { return globalThis.sessionStorage || null } catch { return null }
}

export function useItemPolish({ storage: explicitStorage } = {}) {
  const storage = availableStorage(explicitStorage)
  const intents = reactive({})
  const tasks = reactive({})
  const pollMessages = reactive({})
  const conflicts = reactive({})
  const conflictRefreshMessages = reactive({})
  const conflictRefreshing = reactive({})
  const reconcileBusyGoods = reactive({})
  const reconcileMessages = reactive({})
  const timers = new Map()
  const retryTimers = new Map()
  const pendingPolls = new Map()
  const pollErrors = new Map()
  const scopeGenerations = new Map()
  let disposed = false

  function scopeGeneration(key) {
    return Number(scopeGenerations.get(key) || 0)
  }

  function advanceScopeGeneration(key) {
    const generation = scopeGeneration(key) + 1
    scopeGenerations.set(key, generation)
    return generation
  }

  function captureScopeGuard(key) {
    return { key, generation: scopeGeneration(key) }
  }

  function scopeGuardIsActive(guard) {
    return !disposed
      && guard?.key
      && scopeGeneration(guard.key) === guard.generation
  }

  function persist() {
    if (disposed || !storage) return
    try { storage.setItem(STORAGE_KEY, JSON.stringify(intents)) } catch { /* best effort */ }
  }

  function setTask(scopeKey, rawTask, guard = captureScopeGuard(scopeKey)) {
    if (!scopeGuardIsActive(guard)) return tasks[scopeKey] || null
    const previous = tasks[scopeKey] || intents[scopeKey]?.task || null
    const task = normalizeItemPolishTask(rawTask, previous)
    tasks[scopeKey] = task
    if (intents[scopeKey]) {
      intents[scopeKey].taskId = task.taskId
      intents[scopeKey].task = task
      intents[scopeKey].updatedAt = Date.now()
      persist()
    }
    scheduleRetryAvailability(scopeKey, task, guard)
    return task
  }

  function scope(accountId, goodsIds = []) {
    return itemPolishScopeKey(accountId, goodsIds)
  }

  function taskFor(accountId, goodsIds = []) {
    return tasks[scope(accountId, goodsIds)] || null
  }

  function intentFor(accountId, goodsIds = [], { forceNew = false } = {}) {
    if (disposed) return null
    const key = scope(accountId, goodsIds)
    if (forceNew || !intents[key]) {
      advanceScopeGeneration(key)
      clearRetryTimer(key)
      intents[key] = createItemPolishIntent(accountId, goodsIds)
      delete tasks[key]
      delete reconcileMessages[key]
      delete reconcileBusyGoods[key]
      persist()
    }
    return { key, intent: intents[key], guard: captureScopeGuard(key) }
  }

  function clearPollTimer(key) {
    const timer = timers.get(key)
    if (timer) clearTimeout(timer)
    timers.delete(key)
  }

  function clearRetryTimer(key) {
    const timer = retryTimers.get(key)
    if (timer) clearTimeout(timer)
    retryTimers.delete(key)
  }

  function scheduleRetryAvailability(key, task, guard = captureScopeGuard(key)) {
    if (!scopeGuardIsActive(guard)) return
    clearRetryTimer(key)
    if (task?.recovery !== 'retry_next_business_day' || !task?.retryAfter) return
    const retryAt = Date.parse(task.retryAfter)
    const delay = retryAt - Date.now()
    if (!Number.isFinite(delay) || delay <= 0) return
    const expectedRetryAfter = task.retryAfter
    retryTimers.set(key, setTimeout(() => {
      retryTimers.delete(key)
      if (!scopeGuardIsActive(guard)) return
      if (tasks[key]?.retryAfter !== expectedRetryAfter) return
      setTask(key, tasks[key], guard)
    }, Math.min(delay + 50, MAX_TIMER_DELAY_MS)))
  }

  function stopPolling(key) {
    clearPollTimer(key)
    pendingPolls.delete(key)
    pollErrors.delete(key)
  }

  function schedulePoll(key, guard = captureScopeGuard(key)) {
    if (!scopeGuardIsActive(guard)) return
    clearPollTimer(key)
    const task = tasks[key]
    if (!itemPolishCanAutoPoll(task) || !task.taskId) return
    if (task.status === 'pending' && (pendingPolls.get(key) || 0) >= MAX_PENDING_POLLS) {
      pollMessages[key] = '执行器尚未接管任务；可点击“继续安全任务”，系统会复用原幂等键且不会重复已开始的平台调用。'
      return
    }
    timers.set(key, setTimeout(() => void pollOnce(key, guard), POLL_INTERVAL_MS))
  }

  async function pollOnce(key, guard = captureScopeGuard(key)) {
    if (!scopeGuardIsActive(guard)) return
    const intent = intents[key]
    const taskId = intent?.taskId || tasks[key]?.taskId
    if (!taskId) return
    try {
      const response = await getItemPolishProgress(taskId)
      if (!scopeGuardIsActive(guard)) return
      const task = setTask(key, response?.data || response, guard)
      delete conflicts[key]
      delete conflictRefreshMessages[key]
      delete conflictRefreshing[key]
      pollMessages[key] = ''
      pollErrors.set(key, 0)
      if (task.status === 'pending') {
        pendingPolls.set(key, (pendingPolls.get(key) || 0) + 1)
      } else {
        pendingPolls.set(key, 0)
      }
      schedulePoll(key, guard)
    } catch {
      if (!scopeGuardIsActive(guard)) return
      // A failed GET is not evidence that the task failed. Keep the last
      // confirmed task snapshot and retry only the read a bounded number.
      const count = (pollErrors.get(key) || 0) + 1
      pollErrors.set(key, count)
      pollMessages[key] = '进度暂时无法刷新，已保留上次状态；不会因此重复提交擦亮。'
      if (count < MAX_POLL_ERRORS) {
        timers.set(key, setTimeout(() => void pollOnce(key, guard), POLL_INTERVAL_MS * 2))
      }
    }
  }

  async function submit({ accountId, goodsIds = [], forceNew = false } = {}) {
    if (disposed) return null
    const normalizedGoods = normalizePolishGoodsIds(goodsIds)
    const existing = taskFor(accountId, normalizedGoods)
    if (itemPolishBlocksRetry(existing)) {
      const blocked = new Error(
        itemPolishRetryGuidance(existing)
          || '该擦亮任务仍有未知结果，已安全阻止重复提交。',
      )
      blocked.code = 'ITEM_POLISH_RETRY_BLOCKED'
      blocked.data = existing
      throw blocked
    }
    const shouldCreate = forceNew || itemPolishShouldCreateNewIntent(existing)
    const intentState = intentFor(accountId, normalizedGoods, { forceNew: shouldCreate })
    if (!intentState) return null
    const { key, intent, guard } = intentState
    try {
      const response = await runItemPolish({
        xianyuAccountId: Number(accountId),
        idempotencyKey: intent.idempotencyKey,
        goodsIds: normalizedGoods,
      })
      if (!scopeGuardIsActive(guard)) return tasks[key] || null
      const task = setTask(key, response?.data || response, guard)
      delete conflicts[key]
      delete conflictRefreshMessages[key]
      delete conflictRefreshing[key]
      pendingPolls.set(key, 0)
      pollErrors.set(key, 0)
      pollMessages[key] = ''
      schedulePoll(key, guard)
      return task
    } catch (error) {
      if (!scopeGuardIsActive(guard)) throw error
      const serverTask = error?.data?.existingTask
      if (serverTask) {
        const classified = classifyItemPolishExistingTask(intent, serverTask)
        if (classified.sameIntent) {
          const task = setTask(key, classified.existingTask, guard)
          delete conflicts[key]
          delete conflictRefreshMessages[key]
          delete conflictRefreshing[key]
          if (itemPolishCanAutoPoll(task)) schedulePoll(key, guard)
          return task
        }
        conflicts[key] = classified
        conflictRefreshMessages[key] = ''
        pollMessages[key] = classified.message
        throw { ...error, polishConflict: classified }
      }
      if (error?.timeout || ['TIMEOUT', 'NETWORK_ERROR'].includes(error?.code)) {
        setTask(key, {
          ...(tasks[key] || {}),
          taskId: intent.taskId || tasks[key]?.taskId || '',
          accountId: Number(accountId),
          idempotencyKey: intent.idempotencyKey,
          status: 'pending',
          recovery: 'resume_task',
          retrySafe: true,
          message: '提交结果未确认；系统保留原幂等键，请使用“继续安全任务”恢复，不会生成新意图。',
        }, guard)
      } else if (error?.data?.status) {
        setTask(key, { ...(tasks[key] || {}), ...error.data }, guard)
      }
      throw error
    }
  }

  async function refresh(accountId, goodsIds = []) {
    if (disposed) return null
    const key = scope(accountId, goodsIds)
    const guard = captureScopeGuard(key)
    const taskId = intents[key]?.taskId || tasks[key]?.taskId
    if (!taskId) return tasks[key] || null
    const response = await getItemPolishProgress(taskId)
    if (!scopeGuardIsActive(guard)) return tasks[key] || null
    return setTask(key, response?.data || response, guard)
  }

  async function reconcile({ accountId, goodsIds = [], goodsId, outcome } = {}) {
    if (disposed) return null
    const key = scope(accountId, goodsIds)
    const guard = captureScopeGuard(key)
    const currentTask = tasks[key]
    const payload = createItemPolishReconcilePayload(currentTask, goodsId, outcome)
    if (reconcileBusyGoods[key]) return currentTask
    reconcileBusyGoods[key] = Number(goodsId)
    reconcileMessages[key] = ''
    try {
      const response = await reconcileItemPolish(payload)
      if (!scopeGuardIsActive(guard)) return currentTask
      const nextTask = setTask(key, response?.data?.data || response?.data || response, guard)
      reconcileMessages[key] = ''
      return nextTask
    } catch (error) {
      if (!scopeGuardIsActive(guard)) throw error
      reconcileMessages[key] = '人工核对结论保存失败，已保留原任务快照；请确认网络恢复后仅重试当前这一项。'
      throw error
    } finally {
      if (scopeGuardIsActive(guard)) delete reconcileBusyGoods[key]
    }
  }

  function reconcilingGoodsIdFor(accountId, goodsIds = []) {
    return Number(reconcileBusyGoods[scope(accountId, goodsIds)] || 0)
  }

  function reconcileMessageFor(accountId, goodsIds = []) {
    return reconcileMessages[scope(accountId, goodsIds)] || ''
  }

  async function restore() {
    if (disposed || !storage) return
    try {
      const saved = JSON.parse(storage.getItem(STORAGE_KEY) || '{}')
      if (!saved || typeof saved !== 'object') return
      for (const [key, value] of Object.entries(saved)) {
        if (disposed) return
        if (!value || typeof value !== 'object' || !value.idempotencyKey) continue
        advanceScopeGeneration(key)
        const guard = captureScopeGuard(key)
        intents[key] = value
        if (value.task) {
          tasks[key] = normalizeItemPolishTask(value.task)
          scheduleRetryAvailability(key, tasks[key], guard)
        }
      }
      for (const [key, intent] of Object.entries(intents)) {
        if (disposed) return
        if (!intent.taskId) continue
        const guard = captureScopeGuard(key)
        try {
          const response = await getItemPolishProgress(intent.taskId)
          if (disposed) return
          if (!scopeGuardIsActive(guard)) continue
          const task = setTask(key, response?.data || response, guard)
          // Restored pending tasks require an explicit safe-resume click.
          // Running tasks may continue read-only polling.
          if (task.status === 'running') schedulePoll(key, guard)
        } catch {
          if (disposed) return
          if (!scopeGuardIsActive(guard)) continue
          pollMessages[key] = '暂时无法读取已保存的擦亮任务，原幂等键和上次进度已保留。'
        }
      }
    } catch { /* ignore invalid session state */ }
  }

  function pollMessageFor(accountId, goodsIds = []) {
    return pollMessages[scope(accountId, goodsIds)] || ''
  }

  function conflictFor(accountId, goodsIds = []) {
    return conflicts[scope(accountId, goodsIds)] || null
  }

  async function refreshConflict(accountId, goodsIds = []) {
    if (disposed) return null
    const key = scope(accountId, goodsIds)
    const guard = captureScopeGuard(key)
    const conflict = conflicts[key]
    if (!conflict) return null
    conflictRefreshing[key] = true
    conflictRefreshMessages[key] = ''
    try {
      const outcome = await refreshItemPolishConflictState(conflict, getItemPolishProgress)
      if (!scopeGuardIsActive(guard)) return conflict
      if (conflicts[key] !== conflict) return conflicts[key] || null
      if (outcome.refreshed) conflicts[key] = outcome.conflict
      conflictRefreshMessages[key] = outcome.error
      return outcome.conflict
    } finally {
      if (scopeGuardIsActive(guard)) {
        if (conflicts[key]) conflictRefreshing[key] = false
        else delete conflictRefreshing[key]
      }
    }
  }

  function conflictRefreshingFor(accountId, goodsIds = []) {
    return conflictRefreshing[scope(accountId, goodsIds)] === true
  }

  function conflictRefreshMessageFor(accountId, goodsIds = []) {
    return conflictRefreshMessages[scope(accountId, goodsIds)] || ''
  }

  function clearAllConflicts() {
    if (disposed) return
    for (const key of Object.keys(conflicts)) {
      delete conflicts[key]
      delete pollMessages[key]
    }
    for (const key of Object.keys(conflictRefreshMessages)) delete conflictRefreshMessages[key]
    for (const key of Object.keys(conflictRefreshing)) delete conflictRefreshing[key]
  }

  function stopAll() {
    disposed = true
    for (const key of timers.keys()) stopPolling(key)
    for (const key of retryTimers.keys()) clearRetryTimer(key)
  }

  onScopeDispose(stopAll)

  return {
    tasks,
    submit,
    refresh,
    reconcile,
    restore,
    taskFor,
    pollMessageFor,
    conflictFor,
    refreshConflict,
    conflictRefreshingFor,
    conflictRefreshMessageFor,
    clearAllConflicts,
    reconcilingGoodsIdFor,
    reconcileMessageFor,
    stopAll,
  }
}
