<template>
  <div class="layout-grid">
    <div>
      <div v-if="error" class="global-notice error">{{ error }}</div>
      <div v-if="success" class="global-notice success">{{ success }}</div>
      <div class="global-notice scheduler-info" role="status">
        调度服务支持“同步商品”和“同步订单”。旧任务类型不会执行，可在列表中删除后重新创建。
      </div>

      <CardPanel title="定时任务">
        <EmptyState v-if="tasksAvailable === false" icon="⚠️" title="定时任务列表暂不可用" description="当前无法确认是否存在任务，不会把加载失败显示为空列表。">
          <template #actions><AppButton @click="load">重新加载</AppButton></template>
        </EmptyState>
        <BaseTable v-else :columns="columns" :rows="rows">
          <template #taskType="{ row }">
            <div>
              <div class="strong">{{ row.taskTypeLabel }}</div>
              <div class="subtle">{{ row.taskType }}</div>
            </div>
          </template>
          <template #enabled="{ row }">
            <Badge :type="row.enabledBadge">{{ row.enabledText }}</Badge>
          </template>
          <template #lastStatus="{ row }">
            <div>
              <Badge :type="row.lastStatusBadge">{{ row.lastStatusText }}</Badge>
              <div v-if="row.lastResultText" class="subtle result-summary" :title="row.lastResultText">
                {{ row.lastResultText }}
              </div>
            </div>
          </template>
          <template #op="{ row }">
            <div class="inline-actions">
              <button
                class="link"
                type="button"
                :disabled="!row.available || runningTaskId !== null"
                :aria-disabled="!row.available || runningTaskId !== null"
                :title="row.available ? '编辑任务' : '旧任务类型不可编辑'"
                @click.stop="edit(row.raw)"
              >
                编辑
              </button>
              <button
                class="link"
                type="button"
                :disabled="!row.available || runningTaskId !== null"
                :aria-disabled="!row.available || runningTaskId !== null"
                :title="row.available ? '立即同步并等待真实结果' : '该任务类型不可用'"
                @click.stop="run(row.raw.id)"
              >
                {{ runningTaskId === row.raw.id ? '执行中...' : row.available ? '立即执行' : '类型不可用' }}
              </button>
              <button class="link danger-text" @click.stop="remove(row.raw.id)">删除</button>
            </div>
          </template>
        </BaseTable>
        <Pagination v-if="tasksAvailable === true" :total="total" :current="current" :page-size="pageSize" @page-change="goPage" />
      </CardPanel>
    </div>

    <div>
      <CardPanel :title="form.id ? '编辑任务' : '创建任务'">
        <div class="form-field">
          <label>任务名称</label>
          <input ref="taskNameInputRef" v-model="form.taskName" class="input" />
        </div>
        <div class="form-field">
          <label>账号 ID</label>
          <input v-model="form.accountId" class="input" inputmode="numeric" placeholder="必填，例如 8" />
          <span v-if="accountError" class="input-error">{{ accountError }}</span>
        </div>
        <div class="form-field">
          <label>任务类型</label>
          <select v-model="form.taskType" class="input">
            <option v-for="option in taskTypeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>
        <div class="form-field">
          <label>Cron 表达式</label>
          <input v-model="form.cronExpression" class="input" placeholder="*/30 * * * *" />
          <span v-if="cronError" class="input-error">{{ cronError }}</span>
        </div>
        <div class="form-field">
          <label>配置 JSON</label>
          <textarea v-model="form.configJson" class="textarea" rows="8"></textarea>
          <span v-if="jsonError" class="input-error">{{ jsonError }}</span>
        </div>
        <label class="toggle-row">
          <input v-model="form.enabled" type="checkbox" />
          <span>启用自动调度</span>
        </label>
        <div class="inline-actions">
          <AppButton type="primary" :loading="saving" @click="save">
            {{ saving ? '保存中...' : '保存任务' }}
          </AppButton>
          <AppButton @click="reset">重置</AppButton>
        </div>
      </CardPanel>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import CardPanel from '../components/CardPanel.vue'
import BaseTable from '../components/BaseTable.vue'
import Badge from '../components/Badge.vue'
import AppButton from '../components/AppButton.vue'
import Pagination from '../components/Pagination.vue'
import EmptyState from '../components/EmptyState.vue'
import { confirmDelete } from '../utils/confirmAction.js'
import { camelizeKeys, dateTime, recordsOf, totalOf } from '../utils/apiData.js'
import {
  createScheduledTask,
  deleteScheduledTask,
  getScheduledTasks,
  runScheduledTask,
  updateScheduledTask
} from '../api/scheduledTasks.js'
import {
  DEFAULT_SCHEDULED_TASK_TYPES,
  normalizeScheduledTaskPayload,
  normalizeScheduledTaskTypes,
  resolveScheduledTaskHeaderAction,
  taskTypeLabel
} from '../utils/scheduledTaskState.js'

const tasks = ref([])
const total = ref(0)
const current = ref(1)
const pageSize = ref(20)
const saving = ref(false)
const error = ref('')
const success = ref('')
const cronError = ref('')
const jsonError = ref('')
const accountError = ref('')
const runningTaskId = ref(null)
const tasksAvailable = ref(null)
const taskNameInputRef = ref(null)

const form = reactive({
  id: null,
  taskName: '',
  accountId: '',
  taskType: 'sync_goods',
  cronExpression: '*/30 * * * *',
  configJson: '{}',
  enabled: false
})

const taskTypeOptions = normalizeScheduledTaskTypes(DEFAULT_SCHEDULED_TASK_TYPES)

const columns = [
  { key: 'taskName', title: '任务名称' },
  { key: 'accountId', title: '账号 ID' },
  { key: 'taskType', title: '任务类型' },
  { key: 'cronExpression', title: 'Cron' },
  { key: 'enabled', title: '启用状态' },
  { key: 'lastStatus', title: '最近结果' },
  { key: 'lastRunTimeText', title: '上次运行' },
  { key: 'nextRunTimeText', title: '下次运行' },
  { key: 'op', title: '操作' }
]

const rows = computed(() => tasks.value.map(task => {
  const available = task.available !== false && DEFAULT_SCHEDULED_TASK_TYPES.includes(task.taskType)
  const enabled = task.enabled === 1 || task.enabled === true
  return {
    ...task,
    accountId: task.accountId ?? '-',
    taskTypeLabel: taskTypeLabel(task.taskType),
    available,
    enabledText: available ? enabled ? '已启用' : '已禁用' : '类型不可用',
    enabledBadge: available ? enabled ? 'green' : 'gray' : 'red',
    lastStatusText: statusText(task.lastStatus),
    lastStatusBadge: statusBadge(task.lastStatus),
    lastResultText: resultText(task.lastResult),
    lastRunTimeText: dateTime(task.lastRunTime),
    nextRunTimeText: available && enabled ? dateTime(task.nextRunTime) : '-',
    raw: task
  }
}))

function statusText(status) {
  return {
    running: '执行中',
    success: '成功',
    failed: '失败',
    timeout: '超时',
    unavailable: '不可用',
    unsupported: '类型不可用',
    persistence_failed: '状态保存失败'
  }[String(status || '').toLowerCase()] || '尚未执行'
}

function statusBadge(status) {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'success') return 'green'
  if (normalized === 'running') return 'blue'
  if (['failed', 'timeout', 'unavailable', 'unsupported', 'persistence_failed'].includes(normalized)) return 'red'
  return 'gray'
}

function resultText(lastResult) {
  if (!lastResult) return ''
  const value = typeof lastResult === 'string' ? lastResult : JSON.stringify(lastResult)
  return value.length > 120 ? `${value.slice(0, 120)}…` : value
}

function clearNotice() {
  error.value = ''
  success.value = ''
}

function reset() {
  form.id = null
  form.taskName = ''
  form.accountId = ''
  form.taskType = 'sync_goods'
  form.cronExpression = '*/30 * * * *'
  form.configJson = '{}'
  form.enabled = false
  cronError.value = ''
  jsonError.value = ''
  accountError.value = ''
}

function validateCron(cron) {
  if (!cron) return 'Cron 表达式必填'
  const parts = cron.trim().split(/\s+/)
  if (![5, 6].includes(parts.length)) return 'Cron 应为 5 段，或以秒开头的 6 段格式'
  if (!/^[\d*/,\-?\s]+$/.test(cron)) return 'Cron 包含不支持的字符'
  return ''
}

function validateJson(json) {
  if (!json) return ''
  try {
    const value = JSON.parse(json)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return '配置 JSON 必须是对象'
    return ''
  } catch (jsonValidationError) {
    return `无效 JSON：${jsonValidationError.message}`
  }
}

async function load(preserveNotice = false) {
  if (!preserveNotice) clearNotice()
  try {
    const res = await getScheduledTasks({ current: current.value, size: pageSize.value })
    tasks.value = camelizeKeys(recordsOf(res.data))
    total.value = totalOf(res.data, tasks.value.length)
    tasksAvailable.value = true
  } catch (requestError) {
    tasks.value = []
    total.value = 0
    tasksAvailable.value = false
    error.value = requestError.message || '加载定时任务失败'
  }
}

function edit(task) {
  form.id = task.id
  form.taskName = task.taskName || ''
  form.accountId = task.accountId == null ? '' : String(task.accountId)
  form.taskType = task.taskType || 'sync_goods'
  form.cronExpression = task.cronExpression || '*/30 * * * *'
  form.configJson = typeof task.configJson === 'string' ? task.configJson : JSON.stringify(task.configJson || {}, null, 2)
  form.enabled = task.enabled === 1 || task.enabled === true
  cronError.value = ''
  jsonError.value = ''
  accountError.value = ''
}

async function save() {
  if (saving.value) return
  clearNotice()

  cronError.value = validateCron(form.cronExpression)
  jsonError.value = validateJson(form.configJson)
  const accountId = Number(String(form.accountId || '').trim())
  accountError.value = Number.isSafeInteger(accountId) && accountId > 0 ? '' : '账号 ID 必须是正整数'
  if (cronError.value || jsonError.value || accountError.value) return

  saving.value = true
  try {
    const payload = normalizeScheduledTaskPayload(form)
    if (form.id) {
      await updateScheduledTask(form.id, payload)
      success.value = payload.enabled ? '任务已更新并进入自动调度' : '任务已更新并保持禁用'
    } else {
      await createScheduledTask(payload)
      success.value = payload.enabled ? '任务已创建并进入自动调度' : '任务已创建并保持禁用'
    }
    reset()
    await load(true)
  } catch (requestError) {
    error.value = requestError.message || '保存定时任务失败'
  } finally {
    saving.value = false
  }
}

async function run(id) {
  if (runningTaskId.value !== null) return
  clearNotice()
  runningTaskId.value = id
  try {
    const response = await runScheduledTask(id)
    const result = response?.data?.result || {}
    const summary = Object.keys(result).length ? `：${resultText(result)}` : ''
    success.value = `任务 #${id} 执行成功${summary}`
    await load(true)
  } catch (requestError) {
    error.value = requestError.message || `任务 #${id} 执行失败`
    await load(true)
  } finally {
    runningTaskId.value = null
  }
}

async function remove(id) {
  const confirmed = await confirmDelete('定时任务')
  if (!confirmed) return

  clearNotice()
  try {
    await deleteScheduledTask(id)
    success.value = `任务 #${id} 已删除`
    await load(true)
  } catch (requestError) {
    error.value = requestError.message || '删除定时任务失败'
  }
}

function goPage(page) {
  current.value = page
  load()
}

function focusTaskName() {
  taskNameInputRef.value?.focus?.()
}

function onHeaderAction(event) {
  const action = resolveScheduledTaskHeaderAction(event.detail, form)
  if (action === 'new') {
    reset()
    focusTaskName()
    return
  }
  if (action === 'focus-name') {
    error.value = '请先填写任务名称，再保存任务'
    focusTaskName()
    return
  }
  if (action === 'save') {
    save()
    return
  }
  if (action === 'run') {
    run(form.id)
    return
  }
  if (action === 'select-task') {
    error.value = '请先从左侧列表选择一个任务后再执行'
  }
}

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-header-action', onHeaderAction)
})
</script>

<style scoped>
.layout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 18px;
}

.form-field {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
}

.textarea {
  width: 100%;
  min-height: 160px;
  padding: 10px 12px;
  border: 1px solid #d9e2f0;
  border-radius: 10px;
  resize: vertical;
}

.toggle-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.inline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.strong {
  font-weight: 600;
}

.success {
  background: #ecfdf3;
  color: #067647;
  border-color: #abefc6;
}

.scheduler-info {
  background: #eff8ff;
  color: #175cd3;
  border-color: #b2ddff;
}

.result-summary {
  max-width: 220px;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inline-actions .link:disabled {
  cursor: not-allowed;
  color: #98a2b3;
  text-decoration: none;
}

@media (max-width: 1080px) {
  .layout-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .layout-grid > * {
    min-width: 0;
  }
}

/* === 移动端适配 (max-width: 900px) === */
@media (max-width: 900px) {
  .layout-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }
  .form-field {
    gap: 5px;
    margin-bottom: 10px;
  }
  .textarea {
    min-height: 120px;
    padding: 8px 10px;
    border-radius: 8px;
  }
  .toggle-row {
    margin-bottom: 10px;
  }
  .inline-actions {
    gap: 6px;
  }
  .inline-actions :deep(.app-button),
  .inline-actions .link {
    font-size: 13px;
  }
  /* 宽表格横向滚动 */
  :deep(.base-table) {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
  }
  .card-panel,
  .stat-grid > *,
  .stat-row > *,
  .form-grid > *,
  .two-col > *,
  .three-col > * {
    min-width: 0;
  }
}
</style>
