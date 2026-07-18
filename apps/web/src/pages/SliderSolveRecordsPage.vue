<template>
  <div class="grid slider-layout" style="grid-template-columns:minmax(0,1fr) 460px;gap:18px">
    <div>
      <div v-if="loadError" class="global-notice error">滑块记录加载失败：{{ loadError }}</div>
      <div class="grid stat-grid">
        <StatCard title="总记录数" :value="total" change="服务端总数" icon="record" />
        <StatCard title="成功数" :value="successCount" change="本页统计" icon="shield" color="green" />
        <StatCard title="失败数" :value="failedCount" change="本页统计" icon="warning" color="red" />
        <StatCard title="重试中数" :value="retryingCount" change="本页统计" icon="refresh" color="orange" />
      </div>
      <CardPanel title="滑块求解记录" desc="点击表格行查看完整详情">
        <div class="toolbar">
          <select v-model="filters.status" class="input" @change="search">
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="fail">失败</option>
            <option value="retrying">重试中</option>
          </select>
          <select v-model="filters.triggerScene" class="input" @change="search">
            <option value="">全部触发场景</option>
            <option value="manual">手动触发</option>
            <option value="manual_retry">手动重试</option>
            <option value="ws_connect">WS 连接</option>
            <option value="cookie_keepalive">Cookie 保活</option>
            <option value="token_refresh">Token 刷新</option>
          </select>
          <AppButton type="primary" :disabled="loading" @click="search">{{ loading ? '查询中...' : '查询' }}</AppButton>
        </div>
        <BaseTable :columns="cols" :rows="rows" @row-click="showDetail">
          <template #createdAt="{row}">{{ formatDateTime(row.createdAt) }}</template>
          <template #accountId="{row}"><span :title="row.accountId">{{ row.accountId || '-' }}</span></template>
          <template #accountName="{row}"><span :title="row.accountName">{{ row.accountName || '-' }}</span></template>
          <template #openReason="{row}"><span :title="row.openReason" class="cell-truncate">{{ row.openReason || '-' }}</span></template>
          <template #solveReason="{row}"><span :title="row.solveReason" class="cell-truncate">{{ row.solveReason || '-' }}</span></template>
          <template #status="{row}"><Badge :type="statusBadge(row.status)">{{ statusText(row.status) }}</Badge></template>
          <template #failed="{row}">
            <Badge v-if="row.status === 'fail'" type="red">失败</Badge>
            <Badge v-else-if="row.status === 'success'" type="green">成功</Badge>
            <Badge v-else type="orange">重试中</Badge>
          </template>
          <template #failReason="{row}">
            <span v-if="row.status === 'fail' && row.errorMessage" :title="row.errorMessage" class="cell-truncate fail-text">{{ row.errorMessage }}</span>
            <span v-else-if="row.status === 'fail'" class="cell-truncate fail-text">{{ row.result === 'slider_success' ? '滑块已通过但 Cookie Session 已过期' : '滑块验证未通过' }}</span>
            <span v-else>-</span>
          </template>
          <template #empty><EmptyState icon="🧩" title="暂无滑块求解记录" description="滑块验证记录将在此显示。" /></template>
        </BaseTable>
        <Pagination :total="total" :current="current" :page-size="size" @page-change="goPage" />
      </CardPanel>
    </div>
    <div class="right-drawer">
      <template v-if="detail">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <h3>记录详情</h3>
          <button class="modal-close" @click="detail=null"><Icon name="close" /></button>
        </div>
        <p>记录 ID：<b>{{ detail.id || detail.recordId || '-' }}</b></p>
        <div class="grid" style="grid-template-columns:repeat(2,1fr);gap:10px">
          <div class="metric-tile"><span>账号ID</span><b :title="detail.accountId">{{ detail.accountId || '-' }}</b></div>
          <div class="metric-tile"><span>账号名称</span><b :title="detail.accountName">{{ detail.accountName || '-' }}</b></div>
          <div class="metric-tile"><span>处理状态</span><Badge :type="statusBadge(detail.status)">{{ statusText(detail.status) }}</Badge></div>
          <div class="metric-tile"><span>是否失败</span>
            <Badge v-if="detail.status === 'fail'" type="red">失败</Badge>
            <Badge v-else-if="detail.status === 'success'" type="green">成功</Badge>
            <Badge v-else type="orange">重试中</Badge>
          </div>
          <div class="metric-tile"><span>处理结果</span><Badge :type="resultBadge(detail.result)">{{ resultText(detail.result) }}</Badge></div>
          <div class="metric-tile"><span>验证引擎</span><b :title="detail.engine">{{ detail.engine || '-' }}</b></div>
          <div class="metric-tile"><span>触发场景</span><b :title="detail.triggerScene">{{ triggerSceneText(detail.triggerScene) }}</b></div>
          <div class="metric-tile"><span>重试次数</span><b>{{ detail.retryCount ?? 0 }}</b></div>
        </div>
        <div class="option-line"><span>记录时间</span><b>{{ formatDateTime(detail.createdAt) }}</b></div>
        <div class="option-line"><span>更新时间</span><b>{{ formatDateTime(detail.updatedAt) }}</b></div>
        <div class="option-line"><span>事件描述</span><b>{{ detail.eventDesc || '-' }}</b></div>
        <div class="option-line"><span>耗时</span><b>{{ formatDuration(detail.errorMessage) }}</b></div>
        <div class="option-line option-line-block">
          <span>开启原因</span>
          <div class="option-content">{{ detail.openReason || '-' }}</div>
        </div>
        <div class="option-line option-line-block">
          <span>求解原因</span>
          <div class="option-content">{{ detail.solveReason || '-' }}</div>
        </div>
        <div v-if="extractScreenshot(detail.errorMessage)" class="option-line option-line-block">
          <span>调试截图</span>
          <div class="option-content mono">{{ extractScreenshot(detail.errorMessage) }}</div>
        </div>
        <div v-if="detail.status === 'fail'" class="error-message">
          <div class="error-message-head">失败原因</div>
          <pre class="error-message-body">{{ stripMeta(detail.errorMessage) || (detail.result === 'slider_success' ? '滑块已通过但 Cookie Session 已过期，需重新扫码登录' : '滑块验证未通过') }}</pre>
        </div>
        <div v-else-if="detail.status === 'success' && stripMeta(detail.errorMessage)" class="option-line option-line-block">
          <span>备注</span>
          <div class="option-content">{{ stripMeta(detail.errorMessage) }}</div>
        </div>
      </template>
      <EmptyState v-else icon="🧩" title="选择记录查看详情" description="点击左侧列表中的任意一行，这里会展示该滑块求解记录的完整信息。" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import StatCard from '../components/StatCard.vue'
import CardPanel from '../components/CardPanel.vue'
import BaseTable from '../components/BaseTable.vue'
import Badge from '../components/Badge.vue'
import AppButton from '../components/AppButton.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import Icon from '../components/Icon.vue'
import { getCaptchaRecords } from '../api/captcha.js'

const loading = ref(false)
const loadError = ref('')
const rows = ref([])
const total = ref(0)
const current = ref(1)
const size = ref(20)
const detail = ref(null)
const filters = reactive({ status: '', triggerScene: '' })

const cols = [
  { key: 'createdAt', title: '记录时间' },
  { key: 'accountId', title: '账号ID' },
  { key: 'accountName', title: '账号名称' },
  { key: 'openReason', title: '开启原因' },
  { key: 'solveReason', title: '求解原因' },
  { key: 'status', title: '求解状态' },
  { key: 'failed', title: '是否失败' },
  { key: 'failReason', title: '失败原因' }
]

const successCount = computed(() => rows.value.filter(r => r.status === 'success').length)
const failedCount = computed(() => rows.value.filter(r => r.status === 'fail').length)
const retryingCount = computed(() => rows.value.filter(r => r.status === 'retrying').length)

function resultText(result) {
  if (result === 'slider_success') return '滑块成功'
  if (result === 'slider_fail') return '滑块失败'
  return '未求解'
}
function resultBadge(result) {
  if (result === 'slider_success') return 'green'
  if (result === 'slider_fail') return 'red'
  return 'gray'
}
function statusText(status) {
  if (status === 'success') return '成功'
  if (status === 'fail') return '失败'
  if (status === 'retrying') return '重试中'
  return status || '-'
}
function statusBadge(status) {
  if (status === 'success') return 'green'
  if (status === 'fail') return 'red'
  if (status === 'retrying') return 'orange'
  return 'gray'
}
function triggerSceneText(scene) {
  const map = {
    manual: '手动触发',
    manual_retry: '手动重试',
    ws_connect: 'WS 连接',
    cookie_keepalive: 'Cookie 保活',
    token_refresh: 'Token 刷新',
  }
  return map[scene] || scene || '-'
}

function formatDateTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').replace(/\.\d+$/, '').slice(0, 19)
}

/** 从 error_message 元数据前缀解析 durationMs */
function formatDuration(errorMessage) {
  const m = String(errorMessage || '').match(/durationMs=(\d+)/i)
  if (!m) return '-'
  const ms = Number(m[1])
  if (!Number.isFinite(ms) || ms < 0) return '-'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

function extractScreenshot(errorMessage) {
  const m = String(errorMessage || '').match(/screenshot=([^\s\]]+)/i)
  return m ? m[1] : ''
}

function stripMeta(errorMessage) {
  if (!errorMessage) return ''
  return String(errorMessage).replace(/^\[[^\]]*\]\s*/, '').trim()
}

async function load() {
  loading.value = true
  loadError.value = ''
  rows.value = []
  total.value = 0
  detail.value = null
  try {
    const params = {
      page: current.value,
      pageSize: size.value,
      status: filters.status,
    }
    if (filters.triggerScene) params.triggerScene = filters.triggerScene
    const res = await getCaptchaRecords(params)
    // 开源版无 Java 网关拆包，直接返回 { code, data: { list, total, ... } }
    const payload = res?.data?.list || res?.data?.total != null ? res.data : (res || {})
    const list = Array.isArray(payload.list) ? payload.list : []
    rows.value = list
    total.value = Number(payload.total) || 0
  } catch (e) {
    loadError.value = e?.message || '滑块记录加载失败'
  } finally {
    loading.value = false
  }
}

function goPage(p) {
  current.value = p
  load()
}

function search() {
  current.value = 1
  load()
}

function showDetail(row) { detail.value = row }

// ============================================================
// SSE 事件监听：收到 captcha_solve 事件时自动刷新记录列表
// ============================================================
// 用户反馈：手动点击滑块求解后，本页未显示新增记录。
// 原因：页面仅在 onMounted 时加载一次，不感知后端写入的新记录。
// 修复：监听全局 SSE 事件 captcha_solve（与 useCaptchaSolver.js 一致的事件源），
//       收到事件后刷新列表。为避免 retrying→success/fail 两次事件导致重复请求，加 800ms 防抖。
let refreshTimer = null
function scheduleRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => {
    refreshTimer = null
    // 仅当用户未离开本页且非查询中时刷新，避免与手动查询冲突
    if (!loading.value) load()
  }, 800)
}

function onSseCaptchaSolve(event) {
  const evtDetail = event?.detail
  const data = evtDetail?.payload || evtDetail || {}
  const eventType = evtDetail?.type || data.type || ''
  if (eventType !== 'captcha_solve') return
  scheduleRefresh()
}

onMounted(() => {
  load()
  window.addEventListener('xya-sse-event', onSseCaptchaSolve)
})

onUnmounted(() => {
  window.removeEventListener('xya-sse-event', onSseCaptchaSolve)
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.slider-layout :deep(.stat-grid) {
  grid-template-columns: repeat(4, 1fr);
}
@media (max-width: 1500px) {
  .slider-layout :deep(.stat-grid) {
    grid-template-columns: repeat(2, 1fr);
  }
}
.slider-layout :deep(.base-table tbody tr) {
  cursor: pointer;
  transition: background .15s;
}
.slider-layout :deep(.base-table tbody tr:hover) {
  background: #f3f8ff;
}
.cell-truncate {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.fail-text {
  color: #ef4444;
}
.option-line-block {
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}
.option-line-block .option-content {
  width: 100%;
  padding: 8px 12px;
  background: #f6f8fa;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #475569;
  word-break: break-word;
  white-space: pre-wrap;
}
.error-message {
  margin-top: 14px;
  border: 1px solid #ffd1d1;
  border-radius: 10px;
  background: linear-gradient(135deg, #fff8f8, #fff5f5);
  overflow: hidden;
}
.error-message-head {
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 700;
  color: #ef4444;
  border-bottom: 1px solid #ffd1d1;
}
.error-message-body {
  margin: 0;
  padding: 12px 14px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  color: #526079;
  font-family: inherit;
}
</style>
