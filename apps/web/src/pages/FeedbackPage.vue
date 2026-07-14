<template>
  <div class="feedback-page">
    <div v-if="notice.text" :class="['global-notice', notice.type]">{{ notice.text }}</div>
    <div v-if="feedbackStorageMode === 'bridge'" class="global-notice info">
      反馈将同步发送到商业版后端，由维护团队统一查看和处理。
    </div>
    <div v-else-if="feedbackStorageMode === 'local'" class="global-notice warn">
      当前未配置商业版桥接，反馈仅保存在本地数据库，不会发送到商业版后端；请由部署管理员在本页查看和处理。
    </div>
    <div v-else-if="feedbackStorageMode === 'unknown'" class="global-notice warn">
      当前无法读取反馈记录，但反馈仍只会保存在本地部署，不会转交任何外部服务。
    </div>

    <section class="fbk-hero">
      <div class="fbk-hero-copy">
        <span class="fbk-hero-pill">Feedback Center</span>
        <h2>反馈建议</h2>
        <p>集中记录 Bug、功能建议与流程改进想法，反馈将同步至商业版后端由维护团队处理。</p>

        <div class="fbk-hero-actions">
          <button type="button" class="fbk-btn-primary" @click="openSubmitModal">
            <span class="fbk-plus">+</span>
            <span>提交反馈</span>
          </button>
          <button type="button" class="fbk-btn-ghost" @click="setStatusFilter('open')">查看待处理</button>
        </div>

        <div class="fbk-response-banner">
          <strong>{{ storageModeTitle }}</strong>
          <span>{{ storageModeDescription }}</span>
        </div>
      </div>

      <div class="fbk-hero-side">
        <div class="fbk-stat-grid">
          <button
            type="button"
            class="fbk-stat-card is-total"
            :class="{ active: filter.status === '' }"
            @click="setStatusFilter('')"
          >
            <small>全部反馈</small>
            <strong>{{ statsMetric(stats.total) }}</strong>
            <span>查看全部记录</span>
          </button>
          <button
            type="button"
            class="fbk-stat-card is-open"
            :class="{ active: filter.status === 'open' }"
            @click="setStatusFilter('open')"
          >
            <small>待处理</small>
            <strong>{{ statsMetric(stats.open) }}</strong>
            <span>等待部署管理员处理</span>
          </button>
          <button
            type="button"
            class="fbk-stat-card is-progress"
            :class="{ active: filter.status === 'in_progress' }"
            @click="setStatusFilter('in_progress')"
          >
            <small>处理中</small>
            <strong>{{ statsMetric(stats.inProgress) }}</strong>
            <span>已标记为处理中</span>
          </button>
          <button
            type="button"
            class="fbk-stat-card is-replied"
            :class="{ active: filter.status === 'replied' }"
            @click="setStatusFilter('replied')"
          >
            <small>已回复</small>
            <strong>{{ statsMetric(stats.replied) }}</strong>
            <span>已有结果同步</span>
          </button>
        </div>
      </div>
    </section>

    <div class="fbk-main-grid">
      <section class="fbk-board">
        <div class="fbk-board-head">
          <div>
            <span class="fbk-board-eyebrow">反馈看板</span>
            <h3>{{ activeStatusLabel }}反馈</h3>
            <p>按状态和分类快速查看处理进度，点击卡片可以进入详情并继续补充信息。</p>
          </div>
          <div class="fbk-board-tools">
            <select v-model="filter.category" class="fbk-select" @change="onFilterChange">
              <option value="">全部分类</option>
              <option v-for="c in categoryOptions" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
            <button type="button" class="fbk-icon-btn" title="刷新" @click="reloadAll">↻</button>
          </div>
        </div>

        <div class="fbk-status-filter">
          <button
            v-for="opt in statusFilterOptions"
            :key="opt.value"
            type="button"
            :class="['fbk-pill', { active: filter.status === opt.value }]"
            @click="setStatusFilter(opt.value)"
          >
            {{ opt.label }}
            <span class="fbk-pill-count">{{ statsAvailable ? (opt.value ? (statsByStatus[opt.value] ?? 0) : stats.total) : '—' }}</span>
          </button>
        </div>

        <div v-if="loading.list" class="fbk-state">加载中...</div>

        <EmptyState
          v-else-if="listAvailable === false"
          variant="default"
          icon="⚠️"
          title="反馈列表暂不可用"
          description="当前无法确认是否存在反馈记录，不会把查询失败显示为“还没有反馈”。"
        >
          <template #actions>
            <button type="button" class="fbk-btn-primary" @click="reloadList">重新加载</button>
          </template>
        </EmptyState>

        <EmptyState
          v-else-if="listAvailable === true && !feedbackList.length"
          variant="default"
          icon="📭"
          title="还没有反馈记录"
          description="提交后仅保存在本部署，请确保部署管理员会查看。"
        >
          <template #actions>
            <button type="button" class="fbk-btn-primary" @click="openSubmitModal">去提交反馈</button>
          </template>
        </EmptyState>

        <div v-else-if="listAvailable === true" class="fbk-list">
          <article
            v-for="item in feedbackList"
            :key="item.id"
            :class="['fbk-row', `is-${item.status}`]"
            @click="openDetail(item)"
          >
            <div class="fbk-row-top">
              <div class="fbk-row-badges">
                <span :class="['fbk-category-pill', `cat-${item.category || 'other'}`]">
                  {{ categoryMeta[item.category]?.icon || '📌' }}
                  {{ categoryMeta[item.category]?.label || '其他' }}
                </span>
                <span :class="['fbk-tag', `tag-${item.status}`]">{{ statusMeta[item.status]?.label || '待处理' }}</span>
              </div>
              <span class="fbk-meta-id">#{{ item.id }}</span>
            </div>

            <div class="fbk-row-body">
              <h3 class="fbk-row-title">{{ item.title }}</h3>
              <p class="fbk-row-desc">{{ item.contentPreview || '（无内容预览）' }}</p>
            </div>

            <div class="fbk-row-foot">
              <div class="fbk-row-meta">
                <span>{{ formatTime(item.createdTime) }}</span>
                <span class="sep">·</span>
                <span v-if="item.replierUsername" class="replied">已有回复</span>
                <span v-else>等待处理</span>
              </div>
              <span class="fbk-row-link">查看详情 ›</span>
            </div>
          </article>
        </div>

        <div v-if="listAvailable === true && (feedbackList.length || filter.current > 1)" class="fbk-pagination-wrap">
          <Pagination
            :total="filter.total"
            :current="filter.current"
            :page-size="filter.size"
            :sizes="[10, 20, 50]"
            @page-change="onPageChange"
            @size-change="onSizeChange"
          />
        </div>
      </section>

      <aside class="fbk-side-panel">
        <article class="fbk-side-card emphasis">
          <span class="fbk-side-kicker">提交提示</span>
          <h3>先写清楚，再提交</h3>
          <p>高质量反馈通常包含“发生了什么、如何复现、期望看到什么”，这样能大幅缩短来回确认时间。</p>
          <button type="button" class="fbk-inline-link" @click="openSubmitModal">现在去写反馈</button>
        </article>

        <article class="fbk-side-card">
          <div class="fbk-side-head">
            <strong>提交前建议</strong>
            <span>让处理更快</span>
          </div>
          <ul class="fbk-side-list">
            <li>标题尽量一句话说清问题核心或需求目标。</li>
            <li>正文里优先写具体场景、复现步骤和期望结果。</li>
            <li>如果涉及联调，附上时间点、接口或页面位置会更高效。</li>
          </ul>
        </article>

        <article class="fbk-side-card">
          <div class="fbk-side-head">
            <strong>处理流程</strong>
            <span>一眼看懂进度</span>
          </div>
          <div class="fbk-process">
            <div class="fbk-process-item">
              <b>01</b>
              <div>
                <strong>待处理</strong>
                <p>收到反馈，确认信息是否完整。</p>
              </div>
            </div>
            <div class="fbk-process-item">
              <b>02</b>
              <div>
                <strong>处理中</strong>
                <p>开始排查、设计或联调，并同步进度。</p>
              </div>
            </div>
            <div class="fbk-process-item">
              <b>03</b>
              <div>
                <strong>已回复</strong>
                <p>已经给出结果、结论或后续安排。</p>
              </div>
            </div>
          </div>
        </article>

        <article class="fbk-side-card">
          <div class="fbk-side-head">
            <strong>优先级说明</strong>
            <span>帮助你判断紧急程度</span>
          </div>
          <div class="fbk-priority-grid">
            <div class="fbk-priority-item high">
              <strong>高优先</strong>
              <p>阻断流程、核心功能不可用、关键 Bug。</p>
            </div>
            <div class="fbk-priority-item mid">
              <strong>中优先</strong>
              <p>影响体验但仍有替代路径的问题或优化建议。</p>
            </div>
            <div class="fbk-priority-item low">
              <strong>低优先</strong>
              <p>锦上添花型建议、版式优化和长期迭代项。</p>
            </div>
          </div>
        </article>
      </aside>
    </div>

    <div v-if="submitVisible" class="fbk-mask" @click.self="closeSubmitModal">
      <form class="fbk-modal fbk-submit-modal" @submit.prevent="handleSubmit">
        <div class="fbk-modal-head">
          <div>
            <span class="fbk-modal-pill">New Feedback</span>
            <h3>提交新反馈</h3>
          </div>
          <button type="button" class="fbk-close" aria-label="关闭" @click="closeSubmitModal">×</button>
        </div>

        <div class="fbk-modal-body">
          <div class="fbk-modal-tip">
            <strong>{{ feedbackCreateIntent.pending ? '原反馈结果尚未确认' : '写得越具体，处理越快' }}</strong>
            <p v-if="feedbackCreateIntent.pending">当前只允许复用同一持久化幂等键和原内容重试，禁止创建新反馈意图。</p>
            <p v-else>建议说明“发生了什么、怎么复现、你期待的结果是什么”。如果涉及联调，也可以附上联系方式。</p>
          </div>

          <div class="fbk-field">
            <label class="fbk-label">反馈类型 <span class="req">*</span></label>
            <div class="fbk-cat-row">
              <button
                v-for="c in categoryOptions"
                :key="c.value"
                type="button"
                :class="['fbk-cat-btn', { active: form.category === c.value }]"
                :disabled="loading.submit || feedbackCreateIntent.pending"
                @click="form.category = c.value"
              >
                <span class="icon">{{ c.icon }}</span>
                <span>{{ c.label }}</span>
              </button>
            </div>
          </div>

          <div class="fbk-field">
            <label class="fbk-label" for="fbk-title">标题 <span class="req">*</span></label>
            <input
              id="fbk-title"
              v-model="form.title"
              type="text"
              class="fbk-input"
              placeholder="一句话概括你的反馈"
              maxlength="200"
              :disabled="loading.submit || feedbackCreateIntent.pending"
            />
          </div>

          <div class="fbk-field">
            <label class="fbk-label" for="fbk-content">详细描述 <span class="req">*</span></label>
            <textarea
              id="fbk-content"
              v-model="form.content"
              class="fbk-textarea"
              rows="5"
              placeholder="描述具体场景、复现步骤、期望结果或建议方案"
              maxlength="5000"
              :disabled="loading.submit || feedbackCreateIntent.pending"
            ></textarea>
            <div class="fbk-counter">{{ form.content.length }} / 5000</div>
          </div>

          <div class="fbk-field">
            <label class="fbk-label" for="fbk-contact">联系方式 <span class="fbk-optional">选填</span></label>
            <input
              id="fbk-contact"
              v-model="form.contact"
              type="text"
              class="fbk-input"
              placeholder="手机号 / 邮箱 / 微信，便于我们联系你"
              maxlength="200"
              :disabled="loading.submit || feedbackCreateIntent.pending"
            />
          </div>
        </div>

        <div class="fbk-modal-foot">
          <button type="button" class="fbk-btn-ghost" :disabled="loading.submit || feedbackCreateIntent.pending" @click="resetForm">清空</button>
          <button type="submit" class="fbk-btn-primary" :disabled="loading.submit">
            {{ loading.submit ? '提交中...' : (feedbackCreateIntent.pending ? '复用原反馈意图重试' : '提交反馈') }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="detailVisible" class="fbk-mask" @click.self="closeDetail">
      <div class="fbk-modal fbk-detail-modal">
        <div class="fbk-modal-head">
          <div v-if="detailAvailable === true" class="fbk-detail-meta">
            <span :class="['fbk-category-pill', `cat-${detail.category || 'other'}`]">
              {{ categoryMeta[detail.category]?.icon }} {{ categoryMeta[detail.category]?.label || '其他' }}
            </span>
            <span :class="['fbk-tag', `tag-${detail.status}`]">{{ statusMeta[detail.status]?.label || '待处理' }}</span>
            <span class="fbk-detail-id">#{{ detail.id }}</span>
          </div>
          <button type="button" class="fbk-close" aria-label="关闭" @click="closeDetail">×</button>
        </div>

        <div v-if="detailLoading" class="fbk-state">详情加载中...</div>
        <EmptyState v-else-if="detailAvailable === false" icon="⚠️" title="反馈详情暂不可用" description="当前无法确认回复与补充记录，追加操作已禁用。">
          <template #actions><button type="button" class="fbk-btn-primary" @click="reloadDetail">重新加载详情</button></template>
        </EmptyState>

        <template v-else-if="detailAvailable === true">
        <div class="fbk-modal-body fbk-detail-body">
          <h2 class="fbk-detail-title">{{ detail.title }}</h2>
          <div class="fbk-detail-sub">
            <span>{{ detail.username || '我' }}</span>
            <span class="sep">·</span>
            <span>{{ formatTime(detail.createdTime) }}</span>
            <template v-if="detail.contact">
              <span class="sep">·</span>
              <span>联系方式：{{ detail.contact }}</span>
            </template>
          </div>

          <section class="fbk-msg fbk-msg-mine">
            <div class="fbk-msg-avatar">我</div>
            <div class="fbk-msg-bubble">
              <p class="fbk-msg-text">{{ detail.content }}</p>
              <div class="fbk-msg-time">{{ formatTime(detail.createdTime) }}</div>
            </div>
          </section>

          <section
            v-for="reply in detail.replies || []"
            :key="reply.id"
            :class="['fbk-msg', reply.replierRole === 'admin' ? 'fbk-msg-admin' : 'fbk-msg-mine']"
          >
            <div class="fbk-msg-avatar" :class="{ admin: reply.replierRole === 'admin' }">
              {{ reply.replierRole === 'admin' ? '客服' : '我' }}
            </div>
            <div class="fbk-msg-bubble" :class="{ admin: reply.replierRole === 'admin' }">
              <div class="fbk-msg-label">
                {{ reply.replierRole === 'admin' ? (reply.replierUsername || '管理员') + ' 回复' : '补充说明' }}
              </div>
              <p class="fbk-msg-text">{{ reply.content }}</p>
              <div class="fbk-msg-time">{{ formatTime(reply.createdTime) }}</div>
            </div>
          </section>

          <div v-if="!detail.replies || !detail.replies.length" class="fbk-no-reply">
            暂无回复，请耐心等待
          </div>
        </div>

        <div class="fbk-modal-foot fbk-detail-foot">
          <textarea
            v-model="appendContent"
            class="fbk-textarea fbk-append"
            rows="2"
            placeholder="补充信息、追问进展..."
            maxlength="2000"
            :disabled="loading.append || feedbackReplyIntent.pending"
          ></textarea>
          <div class="fbk-detail-actions">
            <span class="fbk-counter">{{ appendContent.length }} / 2000</span>
            <button
              type="button"
              class="fbk-btn-primary"
              :disabled="loading.append || !appendContent.trim()"
              @click="handleAppend"
            >
              {{ loading.append ? '发送中...' : (feedbackReplyIntent.pending ? '复用原补充意图重试' : '追加补充') }}
            </button>
          </div>
        </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import { submitFeedback, listMyFeedback, getFeedbackDetail, appendFeedbackReply, getFeedbackStats } from '../api/feedback.js'
import { withBrowserIntentLock } from '../utils/browserIntentLock.js'

const notice = ref({ text: '', type: 'info' })
const feedbackStorageMode = ref('local')
const listAvailable = ref(null)
const statsAvailable = ref(false)
const detailAvailable = ref(null)
const detailLoading = ref(false)

const categoryOptions = [
  { value: 'bug', label: '问题反馈', icon: '🐞' },
  { value: 'feature', label: '功能建议', icon: '✨' },
  { value: 'suggestion', label: '改进提议', icon: '💡' },
  { value: 'other', label: '其他', icon: '📌' }
]
const categoryMeta = {
  bug: { label: '问题反馈', icon: '🐞' },
  feature: { label: '功能建议', icon: '✨' },
  suggestion: { label: '改进提议', icon: '💡' },
  other: { label: '其他', icon: '📌' }
}
const statusMeta = {
  open: { label: '待处理' },
  in_progress: { label: '处理中' },
  replied: { label: '已回复' },
  closed: { label: '已关闭' }
}
const statusFilterOptions = [
  { value: '', label: '全部' },
  { value: 'open', label: '待处理' },
  { value: 'in_progress', label: '处理中' },
  { value: 'replied', label: '已回复' },
  { value: 'closed', label: '已关闭' }
]

const filter = reactive({
  status: '',
  category: '',
  current: 1,
  size: 10,
  total: 0
})

const feedbackList = ref([])
const loading = reactive({ list: false, submit: false, append: false })
const feedbackCreateIntent = reactive({ pending: false, key: '', payload: null })
const feedbackReplyIntent = reactive({ pending: false, feedbackId: null, key: '', content: '' })
const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9_.:-]{16,128}$/
const FEEDBACK_CREATE_INTENT_STORAGE_KEY = 'xya:feedback-create-intent'
const FEEDBACK_REPLY_INTENT_STORAGE_PREFIX = 'xya:feedback-reply-intent:'

const form = reactive({
  category: 'bug',
  title: '',
  content: '',
  contact: ''
})

const submitVisible = ref(false)
const detailVisible = ref(false)
const detail = ref({})
const appendContent = ref('')

const stats = reactive({ open: 0, inProgress: 0, replied: 0, closed: 0, total: 0 })
const statsByStatus = computed(() => ({
  open: stats.open,
  in_progress: stats.inProgress,
  replied: stats.replied,
  closed: stats.closed
}))

const activeStatusLabel = computed(() => {
  return statusFilterOptions.find((item) => item.value === filter.status)?.label || '全部'
})
const storageModeTitle = computed(() => {
  if (feedbackStorageMode.value === 'bridge') return '当前为商业版桥接模式'
  if (feedbackStorageMode.value === 'unknown') return '存储模式未知'
  return '当前为本地记录模式'
})
const storageModeDescription = computed(() => {
  if (feedbackStorageMode.value === 'bridge') return '反馈将同步发送到商业版后端，由维护团队统一查看和处理。'
  if (feedbackStorageMode.value === 'unknown') return '当前无法确认反馈存储模式，请稍后重试。'
  return '本地记录需要部署管理员主动查看和处理，不会发送到商业版后端。'
})

function statsMetric(value) {
  return statsAvailable.value ? value : '—'
}

function updateStorageMode(mode) {
  const value = String(mode || '').toLowerCase()
  if (value === 'bridge' || value === 'local') {
    feedbackStorageMode.value = value
  } else if (!value) {
    feedbackStorageMode.value = 'local'
  } else {
    feedbackStorageMode.value = 'unknown'
  }
}

function requireFeedbackDetail(data) {
  if (!data || typeof data !== 'object' || !data.id || !statusMeta[data.status] || !Array.isArray(data.replies)) {
    throw new Error('反馈详情响应格式无效')
  }
  return data
}

function showNotice(text, type = 'info', ttl = 4500) {
  notice.value = { text, type }
  if (ttl) setTimeout(() => { if (notice.value.text === text) notice.value = { text: '', type: 'info' } }, ttl)
}

function setStatusFilter(status) {
  filter.status = status
  filter.current = 1
  reloadList()
}

function onFilterChange() {
  filter.current = 1
  reloadList()
}

function onPageChange(p) {
  filter.current = p
  reloadList()
}

function onSizeChange(s) {
  filter.size = s
  filter.current = 1
  reloadList()
}

async function reloadList() {
  loading.list = true
  try {
    const res = await listMyFeedback({
      current: filter.current,
      size: filter.size,
      status: filter.status,
      category: filter.category
    })
    const data = res?.data || {}
    if (!Array.isArray(data.records)) throw new Error('反馈列表响应格式无效')
    updateStorageMode(data.storageMode)
    feedbackList.value = data.records
    filter.total = Number(data.total ?? data.records.length) || 0
    listAvailable.value = true
  } catch (e) {
    showNotice(e?.message || '加载反馈列表失败', 'error')
    feedbackList.value = []
    filter.total = 0
    listAvailable.value = false
  } finally {
    loading.list = false
  }
}

async function reloadStats() {
  try {
    const res = await getFeedbackStats()
    const data = res?.data || {}
    const fields = ['open', 'in_progress', 'replied', 'closed', 'total']
    if (fields.some(field => data[field] == null || !Number.isFinite(Number(data[field])))) {
      throw new Error('反馈统计响应格式无效')
    }
    updateStorageMode(data.storageMode)
    stats.open = Number(data.open)
    stats.inProgress = Number(data.in_progress)
    stats.replied = Number(data.replied)
    stats.closed = Number(data.closed)
    stats.total = Number(data.total)
    statsAvailable.value = true
  } catch {
    statsAvailable.value = false
    showNotice('反馈统计暂不可用；未加载指标以“—”显示。', 'error')
  }
}

async function reloadAll() {
  await Promise.all([reloadList(), reloadStats()])
}

function openSubmitModal() {
  restoreFeedbackCreateIntent()
  submitVisible.value = true
}

function closeSubmitModal() {
  if (loading.submit) return
  submitVisible.value = false
}

function resetForm() {
  if (feedbackCreateIntent.pending) {
    showNotice('原反馈结果尚未确认，禁止清空或更换反馈意图。', 'warn')
    return
  }
  form.category = 'bug'
  form.title = ''
  form.content = ''
  form.contact = ''
}

function newIdempotencyKey(prefix) {
  const randomPart = window.crypto?.randomUUID?.()
    || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
  const key = `${prefix}:${randomPart}`
  return IDEMPOTENCY_KEY_PATTERN.test(key) ? key : ''
}

function restoreFeedbackCreateIntent() {
  try {
    const record = JSON.parse(window.localStorage.getItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY) || 'null')
    if (!record) return
    if (!IDEMPOTENCY_KEY_PATTERN.test(String(record.key || '')) || !record.payload) {
      throw new Error('invalid feedback intent')
    }
    if (record.status === 'confirmed') return
    Object.assign(form, record.payload)
    Object.assign(feedbackCreateIntent, {
      pending: true,
      key: String(record.key),
      payload: record.payload,
    })
  } catch {
    showNotice('浏览器中的反馈意图记录无法校验，已禁止创建新意图；请联系部署管理员处理站点存储。', 'error', 0)
  }
}

function persistFeedbackCreateIntent(payload) {
  const serialized = JSON.stringify(payload)
  try {
    const existing = JSON.parse(window.localStorage.getItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY) || 'null')
    if (existing) {
      if (!IDEMPOTENCY_KEY_PATTERN.test(String(existing.key || '')) || !existing.payload) throw new Error('invalid intent')
      if (existing.status === 'confirmed') {
        if (JSON.stringify(existing.payload) === serialized) {
          showNotice('相同反馈已确认提交，请刷新反馈列表，禁止重复提交。', 'warn', 0)
          return ''
        }
        window.localStorage.removeItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY)
      } else {
        if (JSON.stringify(existing.payload) !== serialized) {
          showNotice('已有结果未确认的反馈；禁止更换内容或生成新幂等键。', 'error', 0)
          return ''
        }
        Object.assign(feedbackCreateIntent, { pending: true, key: String(existing.key), payload: existing.payload })
        return feedbackCreateIntent.key
      }
    }
    const key = newIdempotencyKey('feedback-create')
    if (!key) throw new Error('key generation failed')
    const record = { key, payload, status: 'pending' }
    window.localStorage.setItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY, JSON.stringify(record))
    const confirmed = JSON.parse(window.localStorage.getItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY) || 'null')
    if (confirmed?.key !== key || JSON.stringify(confirmed?.payload) !== serialized) throw new Error('storage verification failed')
    Object.assign(feedbackCreateIntent, { pending: true, key, payload })
    return key
  } catch {
    showNotice('浏览器无法安全保存反馈意图，提交已禁用；请恢复站点存储权限后重试。', 'error', 0)
    return ''
  }
}

function confirmFeedbackCreateIntent(result) {
  try {
    const record = JSON.parse(window.localStorage.getItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY) || 'null')
    if (record?.key === feedbackCreateIntent.key) {
      window.localStorage.setItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY, JSON.stringify({
        key: record.key,
        status: 'confirmed',
        confirmedAt: Date.now(),
        feedbackId: Number(result?.id || 0) || null,
      }))
      window.localStorage.removeItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY)
    }
  } catch { /* original pending record remains fail-closed if storage changed */ }
  feedbackCreateIntent.pending = false
  feedbackCreateIntent.payload = null
}

function clearFeedbackCreateIntent() {
  try { window.localStorage.removeItem(FEEDBACK_CREATE_INTENT_STORAGE_KEY) } catch { /* same key remains fail-closed */ }
  Object.assign(feedbackCreateIntent, { pending: false, key: '', payload: null })
}

function feedbackReplyStorageKey(feedbackId) {
  return `${FEEDBACK_REPLY_INTENT_STORAGE_PREFIX}${feedbackId}`
}

function restoreFeedbackReplyIntent(feedbackId) {
  Object.assign(feedbackReplyIntent, { pending: false, feedbackId: null, key: '', content: '' })
  try {
    const record = JSON.parse(window.localStorage.getItem(feedbackReplyStorageKey(feedbackId)) || 'null')
    if (!record) return
    if (!IDEMPOTENCY_KEY_PATTERN.test(String(record.key || '')) || typeof record.content !== 'string') throw new Error('invalid reply intent')
    if (record.status === 'confirmed') return
    appendContent.value = record.content
    Object.assign(feedbackReplyIntent, {
      pending: true,
      feedbackId,
      key: String(record.key),
      content: record.content,
    })
  } catch {
    showNotice('浏览器中的补充意图记录无法校验，已禁止创建新意图。', 'error', 0)
  }
}

function persistFeedbackReplyIntent(feedbackId, content) {
  const storageKey = feedbackReplyStorageKey(feedbackId)
  try {
    const existing = JSON.parse(window.localStorage.getItem(storageKey) || 'null')
    if (existing) {
      if (!IDEMPOTENCY_KEY_PATTERN.test(String(existing.key || '')) || typeof existing.content !== 'string') throw new Error('invalid reply intent')
      if (existing.status === 'confirmed') {
        if (existing.content === content) {
          showNotice('相同补充说明已确认提交，请刷新详情，禁止重复发送。', 'warn', 0)
          return ''
        }
        window.localStorage.removeItem(storageKey)
      } else {
        if (existing.content !== content) {
          showNotice('已有结果未确认的反馈补充；禁止更换内容或生成新幂等键。', 'error', 0)
          return ''
        }
        Object.assign(feedbackReplyIntent, { pending: true, feedbackId, key: String(existing.key), content })
        return feedbackReplyIntent.key
      }
    }
    const key = newIdempotencyKey(`feedback-reply-${feedbackId}`)
    if (!key) throw new Error('key generation failed')
    const record = { key, content, status: 'pending' }
    window.localStorage.setItem(storageKey, JSON.stringify(record))
    const confirmed = JSON.parse(window.localStorage.getItem(storageKey) || 'null')
    if (confirmed?.key !== key || confirmed?.content !== content) throw new Error('storage verification failed')
    Object.assign(feedbackReplyIntent, { pending: true, feedbackId, key, content })
    return key
  } catch {
    showNotice('浏览器无法安全保存反馈补充意图，本次发送已禁用。', 'error', 0)
    return ''
  }
}

function confirmFeedbackReplyIntent(feedbackId) {
  try {
    const storageKey = feedbackReplyStorageKey(feedbackId)
    const record = JSON.parse(window.localStorage.getItem(storageKey) || 'null')
    if (record?.key === feedbackReplyIntent.key) {
      window.localStorage.setItem(storageKey, JSON.stringify({
        key: record.key,
        status: 'confirmed',
        confirmedAt: Date.now(),
      }))
      window.localStorage.removeItem(storageKey)
    }
  } catch { /* original pending record remains fail-closed if storage changed */ }
  feedbackReplyIntent.pending = false
  feedbackReplyIntent.content = ''
}

function clearFeedbackReplyIntent(feedbackId) {
  try { window.localStorage.removeItem(feedbackReplyStorageKey(feedbackId)) } catch { /* same key remains fail-closed */ }
  Object.assign(feedbackReplyIntent, { pending: false, feedbackId: null, key: '', content: '' })
}

function feedbackWriteDefinitelyNotIssued(error) {
  const status = Number(error?.status || error?.code || 0)
  return status === 400
    || status === 422
}

async function handleSubmit() {
  if (loading.submit) return
  if (!form.title.trim()) {
    showNotice('请填写反馈标题', 'warn')
    return
  }
  if (!form.content.trim()) {
    showNotice('请填写反馈内容', 'warn')
    return
  }
  const payload = {
    category: form.category,
    title: form.title.trim(),
    content: form.content.trim(),
    contact: form.contact.trim()
  }
  let idempotencyKey = ''
  try {
    idempotencyKey = await withBrowserIntentLock(
      'feedback-create-intent',
      () => persistFeedbackCreateIntent(payload),
    )
  } catch (error) {
    showNotice(error?.message || '无法取得跨标签页反馈锁，提交已禁用。', 'error', 0)
  }
  if (!idempotencyKey) return
  loading.submit = true
  try {
    const response = await submitFeedback({ ...payload, idempotencyKey })
    confirmFeedbackCreateIntent(response?.data)
    updateStorageMode(response?.data?.storageMode)
    showNotice('反馈已保存到本部署，请等待部署管理员处理', 'success')
    resetForm()
    submitVisible.value = false
    filter.status = ''
    filter.current = 1
    await reloadAll()
  } catch (e) {
    if (feedbackWriteDefinitelyNotIssued(e)) clearFeedbackCreateIntent()
    showNotice(e?.message || '反馈结果未确认；只能复用原反馈意图重试。', 'error', 0)
  } finally {
    loading.submit = false
  }
}

async function openDetail(item) {
  detail.value = { id: item.id }
  detailVisible.value = true
  appendContent.value = ''
  restoreFeedbackReplyIntent(item.id)
  detailAvailable.value = null
  await reloadDetail()
}

async function reloadDetail() {
  if (!detail.value?.id) return
  detailLoading.value = true
  try {
    const res = await getFeedbackDetail(detail.value.id)
    detail.value = requireFeedbackDetail(res?.data)
    detailAvailable.value = true
  } catch (e) {
    detailAvailable.value = false
    showNotice(e?.message || '加载详情失败', 'error')
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  if (loading.append) return
  detailVisible.value = false
  detail.value = {}
  detailAvailable.value = null
}

async function handleAppend() {
  if (loading.append) return
  if (!appendContent.value.trim() || detailAvailable.value !== true) return
  const content = appendContent.value.trim()
  const feedbackId = detail.value.id
  let idempotencyKey = ''
  try {
    idempotencyKey = await withBrowserIntentLock(
      `feedback-reply-intent:${feedbackId}`,
      () => persistFeedbackReplyIntent(feedbackId, content),
    )
  } catch (error) {
    showNotice(error?.message || '无法取得跨标签页补充锁，本次发送已禁用。', 'error', 0)
  }
  if (!idempotencyKey) return
  loading.append = true
  try {
    await appendFeedbackReply(feedbackId, content, idempotencyKey)
    confirmFeedbackReplyIntent(feedbackId)
    appendContent.value = ''
    showNotice('已追加补充说明', 'success')
    let detailRefreshFailed = false
    try {
      const res = await getFeedbackDetail(detail.value.id)
      detail.value = requireFeedbackDetail(res?.data)
      detailAvailable.value = true
    } catch {
      detailRefreshFailed = true
      detailAvailable.value = false
    }
    await reloadAll()
    if (detailRefreshFailed) {
      showNotice('补充说明已追加，但详情刷新失败。请重新加载详情，勿重复提交。', 'warn', 0)
    }
  } catch (e) {
    if (feedbackWriteDefinitelyNotIssued(e)) clearFeedbackReplyIntent(feedbackId)
    showNotice(e?.message || '补充结果未确认，请先刷新详情核对，勿直接重复提交。', 'error', 0)
  } finally {
    loading.append = false
  }
}

function formatTime(value) {
  if (!value) return ''
  const d = new Date(String(value).replace(' ', 'T'))
  if (isNaN(d.getTime())) return String(value)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const pad = (n) => String(n).padStart(2, '0')
  if (sameDay) return `今天 ${pad(d.getHours())}:${pad(d.getMinutes())}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(() => {
  reloadAll()
})
</script>

<style scoped>
.feedback-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.fbk-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, 1fr);
  gap: 16px;
  padding: 22px;
  border-radius: 26px;
  border: 1px solid rgba(231, 237, 247, 0.96);
  background:
    radial-gradient(circle at top left, rgba(13, 107, 255, 0.12), transparent 32%),
    radial-gradient(circle at top right, rgba(22, 191, 120, 0.08), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(247, 250, 255, 0.96));
  box-shadow: 0 18px 42px rgba(31, 53, 94, 0.08);
}

.fbk-hero-copy {
  min-width: 0;
}

.fbk-hero-pill {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(13, 107, 255, 0.08);
  color: #2c63d4;
  font-size: 11px;
  font-weight: 800;
}

.fbk-hero-copy h2 {
  margin: 12px 0 0;
  font-size: 32px;
  color: #14213d;
}

.fbk-hero-copy p {
  margin: 10px 0 0;
  max-width: 760px;
  color: #60738e;
  line-height: 1.8;
  font-size: 14px;
}

.fbk-hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 18px;
}

.fbk-response-banner {
  margin-top: 18px;
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid rgba(216, 230, 251, 0.98);
  background: linear-gradient(135deg, rgba(241, 247, 255, 0.96), rgba(255, 255, 255, 0.98));
}

.fbk-response-banner strong {
  display: block;
  color: #13213d;
  font-size: 15px;
}

.fbk-response-banner span {
  display: block;
  margin-top: 6px;
  color: #64748b;
  line-height: 1.7;
  font-size: 13px;
}

.fbk-hero-side {
  display: flex;
}

.fbk-stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
}

.fbk-stat-card {
  text-align: left;
  padding: 16px;
  border-radius: 20px;
  border: 1px solid rgba(227, 235, 246, 0.96);
  background: rgba(255, 255, 255, 0.95);
  transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}

.fbk-stat-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 30px rgba(31, 53, 94, 0.07);
}

.fbk-stat-card.active {
  border-color: #bfd5fb;
  box-shadow: 0 0 0 3px rgba(13, 107, 255, 0.08);
}

.fbk-stat-card small {
  display: block;
  color: #7c8aa4;
  font-size: 12px;
  font-weight: 700;
}

.fbk-stat-card strong {
  display: block;
  margin-top: 10px;
  font-size: 30px;
  line-height: 1;
  color: #13213d;
}

.fbk-stat-card span {
  display: block;
  margin-top: 8px;
  color: #6f7f98;
  font-size: 12px;
  line-height: 1.6;
}

.fbk-stat-card.is-total strong {
  color: #0d6bff;
}

.fbk-stat-card.is-open strong {
  color: #d9821f;
}

.fbk-stat-card.is-progress strong {
  color: #1199ba;
}

.fbk-stat-card.is-replied strong {
  color: #16a36a;
}

.fbk-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) 320px;
  gap: 18px;
  align-items: start;
}

.fbk-board,
.fbk-side-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 22px;
  box-shadow: 0 10px 26px rgba(31, 53, 94, 0.055);
}

.fbk-board {
  padding: 20px;
}

.fbk-board-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.fbk-board-eyebrow {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(13, 107, 255, 0.08);
  color: #2c63d4;
  font-size: 11px;
  font-weight: 800;
}

.fbk-board-head h3 {
  margin: 10px 0 0;
  font-size: 22px;
  color: #15213d;
}

.fbk-board-head p {
  margin: 8px 0 0;
  color: #6a7992;
  line-height: 1.7;
  font-size: 13px;
}

.fbk-board-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fbk-status-filter {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #edf2fa;
}

.fbk-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 14px;
  border-radius: 999px;
  background: #f5f8fd;
  border: 1px solid transparent;
  color: #5f708c;
  font-size: 13px;
  font-weight: 700;
  transition: all .16s ease;
}

.fbk-pill:hover {
  background: #eef4ff;
  color: #0d6bff;
}

.fbk-pill.active {
  background: #eaf2ff;
  border-color: #c6dafd;
  color: #0d6bff;
}

.fbk-pill-count {
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.85);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 800;
}

.fbk-select {
  height: 38px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  padding: 0 12px;
  color: #30415c;
}

.fbk-icon-btn {
  width: 38px;
  height: 38px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  color: #60738e;
  font-size: 16px;
  transition: all .16s ease;
}

.fbk-icon-btn:hover {
  background: #f4f8ff;
  color: #0d6bff;
  border-color: #bfd4fb;
  transform: rotate(90deg);
}

.fbk-state {
  padding: 36px;
  text-align: center;
  color: #72809a;
  font-size: 14px;
}

.fbk-list {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.fbk-row {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #e6edf7;
  background: linear-gradient(180deg, #ffffff, #fbfdff);
  transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}

.fbk-row:hover {
  transform: translateY(-1px);
  border-color: #c7d8f0;
  box-shadow: 0 14px 32px rgba(31, 53, 94, 0.07);
}

.fbk-row.is-open {
  border-left: 4px solid #f59e0b;
}

.fbk-row.is-in_progress {
  border-left: 4px solid #11b5d8;
}

.fbk-row.is-replied {
  border-left: 4px solid #16bf78;
}

.fbk-row.is-closed {
  border-left: 4px solid #a3afc2;
}

.fbk-row-top,
.fbk-row-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.fbk-row-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.fbk-category-pill,
.fbk-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.fbk-category-pill {
  background: #f3f6fc;
  color: #5f708c;
}

.fbk-category-pill.cat-bug {
  background: #fff1f1;
  color: #d35353;
}

.fbk-category-pill.cat-feature {
  background: #eef5ff;
  color: #2868d8;
}

.fbk-category-pill.cat-suggestion {
  background: #fff8e8;
  color: #b07418;
}

.fbk-category-pill.cat-other {
  background: #f2f4f8;
  color: #6b7891;
}

.fbk-tag.tag-open {
  background: #fff3e0;
  color: #c47700;
}

.fbk-tag.tag-in_progress {
  background: #e0f7fb;
  color: #0a93b0;
}

.fbk-tag.tag-replied {
  background: #e4f7ed;
  color: #0f9c5e;
}

.fbk-tag.tag-closed {
  background: #eef1f6;
  color: #6c7891;
}

.fbk-meta-id {
  color: #8a97ab;
  font-size: 12px;
  font-weight: 700;
}

.fbk-row-body {
  margin-top: 14px;
}

.fbk-row-title {
  margin: 0;
  color: #15213d;
  font-size: 17px;
  line-height: 1.45;
}

.fbk-row-desc {
  margin: 8px 0 0;
  color: #62748d;
  font-size: 13px;
  line-height: 1.7;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fbk-row-foot {
  margin-top: 14px;
}

.fbk-row-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #7b879c;
  font-size: 12px;
}

.fbk-row-meta .sep {
  color: #c4cde0;
}

.fbk-row-meta .replied {
  color: #11995f;
  font-weight: 700;
}

.fbk-row-link {
  color: #0d6bff;
  font-size: 13px;
  font-weight: 700;
}

.fbk-pagination-wrap {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #edf2fa;
}

.fbk-side-panel {
  display: grid;
  gap: 14px;
}

.fbk-side-card {
  padding: 18px;
}

.fbk-side-card.emphasis {
  background:
    radial-gradient(circle at top right, rgba(13, 107, 255, 0.14), transparent 30%),
    linear-gradient(180deg, rgba(248, 251, 255, 0.98), rgba(255, 255, 255, 0.98));
}

.fbk-side-kicker {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(13, 107, 255, 0.08);
  color: #2c63d4;
  font-size: 11px;
  font-weight: 800;
}

.fbk-side-card h3 {
  margin: 12px 0 0;
  font-size: 20px;
  color: #15213d;
}

.fbk-side-card p {
  margin: 8px 0 0;
  color: #677892;
  line-height: 1.75;
  font-size: 13px;
}

.fbk-inline-link {
  margin-top: 14px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #0d6bff;
  font-weight: 800;
}

.fbk-side-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.fbk-side-head strong {
  color: #15213d;
  font-size: 16px;
}

.fbk-side-head span {
  color: #8a97ab;
  font-size: 12px;
}

.fbk-side-list {
  margin: 14px 0 0;
  padding-left: 18px;
  color: #64748b;
  line-height: 1.8;
  font-size: 13px;
}

.fbk-process {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.fbk-process-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px;
  border-radius: 16px;
  background: #f8fbff;
  border: 1px solid #e6eef9;
}

.fbk-process-item b {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  background: #edf4ff;
  color: #0d6bff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.fbk-process-item strong {
  display: block;
  color: #15213d;
  font-size: 14px;
}

.fbk-process-item p {
  margin-top: 5px;
  font-size: 12.5px;
}

.fbk-priority-grid {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.fbk-priority-item {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #e6eef9;
}

.fbk-priority-item strong {
  display: block;
  font-size: 14px;
}

.fbk-priority-item p {
  margin-top: 6px;
  font-size: 12.5px;
}

.fbk-priority-item.high {
  background: #fff7eb;
  border-color: #ffe4bb;
}

.fbk-priority-item.high strong {
  color: #b86d08;
}

.fbk-priority-item.mid {
  background: #eef6ff;
  border-color: #d4e5ff;
}

.fbk-priority-item.mid strong {
  color: #2868d8;
}

.fbk-priority-item.low {
  background: #f4f7fb;
  border-color: #e2e8f2;
}

.fbk-priority-item.low strong {
  color: #64748b;
}

.fbk-btn-primary,
.fbk-btn-ghost {
  height: 40px;
  padding: 0 16px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: transform .12s ease, box-shadow .16s ease, background .16s ease, border-color .16s ease;
}

.fbk-btn-primary {
  background: linear-gradient(90deg, #0865f4, #147dff);
  border: 1px solid #0865f4;
  color: #fff;
  box-shadow: 0 10px 22px rgba(13, 107, 255, 0.2);
}

.fbk-btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
}

.fbk-btn-ghost {
  background: #fff;
  border: 1px solid var(--line);
  color: #30415c;
}

.fbk-btn-ghost:hover:not(:disabled) {
  background: #f4f8ff;
  border-color: #bfd4fb;
  color: #0d6bff;
}

.fbk-btn-primary:active:not(:disabled),
.fbk-btn-ghost:active:not(:disabled) {
  transform: scale(.98);
}

.fbk-plus {
  font-size: 16px;
  line-height: 1;
}

.fbk-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 28, 51, 0.55);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  animation: fbk-fade .2s ease;
}

@keyframes fbk-fade {
  from { opacity: 0; }
  to { opacity: 1; }
}

.fbk-modal {
  background: #fff;
  border-radius: 24px;
  width: min(720px, 100%);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 60px rgba(15, 28, 51, 0.24);
  overflow: hidden;
  animation: fbk-pop .24s ease;
}

.fbk-detail-modal {
  width: min(760px, 100%);
}

@keyframes fbk-pop {
  from {
    transform: scale(.96);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

.fbk-modal-head {
  padding: 18px 20px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  background: linear-gradient(180deg, #fbfdff, #fff);
}

.fbk-modal-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(13, 107, 255, 0.08);
  color: #2c63d4;
  font-size: 11px;
  font-weight: 800;
}

.fbk-modal-head h3 {
  margin: 10px 0 0;
  font-size: 20px;
  color: #15213d;
}

.fbk-close {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: #71809a;
  font-size: 24px;
}

.fbk-close:hover {
  background: #f2f6fc;
  color: #15213d;
}

.fbk-modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.fbk-modal-foot {
  padding: 14px 20px 18px;
  border-top: 1px solid var(--line);
  background: #fbfdff;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
}

.fbk-detail-foot {
  flex-direction: column;
  align-items: stretch;
}

.fbk-modal-tip {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid #dbe7fb;
  background: linear-gradient(135deg, #f3f8ff, #ffffff);
  margin-bottom: 16px;
}

.fbk-modal-tip strong {
  display: block;
  color: #15213d;
}

.fbk-modal-tip p {
  margin: 6px 0 0;
  color: #64748b;
  line-height: 1.7;
  font-size: 13px;
}

.fbk-field {
  margin-bottom: 14px;
}

.fbk-field:last-child {
  margin-bottom: 0;
}

.fbk-label {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: #15213d;
  margin-bottom: 8px;
}

.req {
  color: #ef4444;
}

.fbk-optional {
  color: #8a97ab;
  font-weight: 500;
  margin-left: 4px;
}

.fbk-cat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
}

.fbk-cat-btn {
  min-height: 42px;
  padding: 0 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: #fff;
  color: #30415c;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  transition: all .16s ease;
}

.fbk-cat-btn:hover {
  background: #f4f8ff;
  border-color: #bfd4fb;
}

.fbk-cat-btn.active {
  background: #eaf2ff;
  border-color: #0d6bff;
  color: #0d6bff;
}

.fbk-input,
.fbk-textarea {
  width: 100%;
  padding: 11px 13px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fff;
  color: #30415c;
  font-size: 14px;
  font-family: inherit;
  transition: border-color .16s ease, box-shadow .16s ease;
}

.fbk-input::placeholder,
.fbk-textarea::placeholder {
  color: #9aa7bc;
}

.fbk-input:focus,
.fbk-textarea:focus {
  outline: none;
  border-color: #0d6bff;
  box-shadow: 0 0 0 4px rgba(13, 107, 255, 0.11);
}

.fbk-textarea {
  min-height: 108px;
  resize: vertical;
  line-height: 1.7;
}

.fbk-counter {
  margin-top: 6px;
  text-align: right;
  color: #8a97ab;
  font-size: 11px;
}

.fbk-detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fbk-detail-id {
  color: #8a97ab;
  font-size: 12px;
  font-weight: 700;
}

.fbk-detail-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fbk-detail-title {
  margin: 0;
  color: #15213d;
  font-size: 20px;
  line-height: 1.45;
}

.fbk-detail-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: #7a879e;
  font-size: 12px;
  padding-bottom: 14px;
  border-bottom: 1px dashed #d8e1ee;
}

.fbk-detail-sub .sep {
  color: #c4cde0;
}

.fbk-msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.fbk-msg-avatar {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: linear-gradient(135deg, #5a9fff, #0d6bff);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.fbk-msg-avatar.admin {
  background: linear-gradient(135deg, #16bf78, #0fa060);
}

.fbk-msg-bubble {
  max-width: 82%;
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid #e4ecf7;
  background: #f7faff;
}

.fbk-msg-bubble.admin {
  background: #edf9f2;
  border-color: #cdebd8;
}

.fbk-msg-label {
  color: #7a879e;
  font-size: 11px;
  font-weight: 700;
  margin-bottom: 4px;
}

.fbk-msg-bubble.admin .fbk-msg-label {
  color: #0f9c5e;
}

.fbk-msg-text {
  margin: 0;
  color: #30415c;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
}

.fbk-msg-time {
  margin-top: 6px;
  color: #8a97ab;
  font-size: 11px;
}

.fbk-no-reply {
  text-align: center;
  padding: 18px;
  border-radius: 16px;
  background: #fbfdff;
  color: #7a879e;
  font-size: 13px;
}

.fbk-append {
  min-height: 64px;
}

.fbk-detail-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}

@media (max-width: 1180px) {
  .fbk-hero,
  .fbk-main-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .fbk-hero-copy,
  .fbk-hero-side,
  .fbk-board,
  .fbk-side-card {
    min-width: 0;
  }
}

@media (max-width: 900px) {
  .fbk-hero {
    padding: 14px;
  }

  .fbk-hero-copy h2 {
    font-size: 22px;
  }

  .fbk-response-banner {
    padding: 12px 14px;
  }

  .fbk-stat-card {
    padding: 12px;
  }

  .fbk-stat-card strong {
    font-size: 22px;
  }

  .fbk-board {
    padding: 14px;
  }

  .fbk-board-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .fbk-board-head h3 {
    font-size: 18px;
  }

  .fbk-row {
    padding: 14px;
  }

  .fbk-row-top,
  .fbk-row-foot {
    flex-wrap: wrap;
    gap: 8px;
  }

  .fbk-side-card {
    padding: 14px;
  }

  .fbk-side-card h3 {
    font-size: 18px;
  }

  .fbk-process-item {
    padding: 12px;
  }

  .fbk-priority-item {
    padding: 12px;
  }

  .fbk-mask {
    padding: 0;
    align-items: flex-end;
  }

  .fbk-modal,
  .fbk-detail-modal {
    width: 100%;
    max-width: 100%;
    max-height: 90vh;
    border-radius: 18px 18px 0 0;
  }

  .fbk-modal-head {
    padding: 14px;
  }

  .fbk-modal-head h3 {
    font-size: 18px;
  }

  .fbk-modal-body {
    padding: 14px;
  }

  .fbk-modal-foot {
    padding: 12px 14px 14px;
  }

  .fbk-detail-title {
    font-size: 18px;
  }

  .fbk-cat-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .fbk-detail-actions {
    flex-wrap: wrap;
  }
}

@media (max-width: 720px) {
  .fbk-hero,
  .fbk-board,
  .fbk-side-card {
    padding: 16px;
  }

  .fbk-stat-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .fbk-board-head,
  .fbk-board-tools,
  .fbk-row-top,
  .fbk-row-foot,
  .fbk-detail-actions {
    flex-direction: column;
    align-items: flex-start;
  }

  .fbk-status-filter {
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 2px;
  }

  .fbk-pill {
    white-space: nowrap;
  }

  .fbk-cat-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .fbk-msg-bubble {
    max-width: 100%;
  }
}
</style>
