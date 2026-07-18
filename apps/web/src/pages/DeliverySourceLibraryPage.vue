<template>
  <div>
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon-circle blue"><span class="stat-icon-svg">📦</span></div>
        <div class="stat-info">
          <div class="stat-label">货源总数</div>
          <div class="stat-value">{{ sourceTotal }}</div>
          <div class="stat-trend muted">统一管理的货源条目</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon-circle green"><span class="stat-icon-svg">📝</span></div>
        <div class="stat-info">
          <div class="stat-label">文本发货</div>
          <div class="stat-value">{{ sourceTotal }}</div>
          <div class="stat-trend muted">固定文案直接发送</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon-circle purple"><span class="stat-icon-svg">🔗</span></div>
        <div class="stat-info">
          <div class="stat-label">已配置商品</div>
          <div class="stat-value">{{ totalConfiguredCount }}</div>
          <div class="stat-trend muted">货源绑定商品总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon-circle orange"><span class="stat-icon-svg">🏷</span></div>
        <div class="stat-info">
          <div class="stat-label">可选商品</div>
          <div class="stat-value">{{ candidateLibraryTotal }}</div>
          <div class="stat-trend muted">可配置的商品池规模</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon-circle" :class="aiStatus.configured ? 'green' : 'gray'"><span class="stat-icon-svg">{{ aiStatus.configured ? '✓' : '!' }}</span></div>
        <div class="stat-info">
          <div class="stat-label">AI 推荐</div>
          <div class="stat-value">{{ aiStatus.configured ? '可用' : '未配置' }}</div>
          <div class="stat-trend" :class="aiStatus.configured ? 'muted' : 'down'">
            {{ aiStatus.configured ? 'AI 模型已就绪' : '请先配置通用模型' }}
          </div>
        </div>
      </div>
    </div>

    <CardPanel title="货源库">
      <div class="toolbar">
        <input v-model="query.keyword" class="input" placeholder="搜索标题 / 正文 / 备注" :disabled="sourcesLoading || Boolean(mutationBusy)" @keyup.enter="searchSources" />
        <AppButton type="primary" :disabled="sourcesLoading || Boolean(mutationBusy)" @click="searchSources">搜索</AppButton>
        <AppButton :disabled="sourcesAvailable !== true || Boolean(mutationBusy)" @click="openCreate">新增货源</AppButton>
      </div>

      <EmptyState v-if="sourcesLoading && sourcesAvailable !== true" icon="⏳" title="货源库加载中" description="正在读取货源与使用情况。" />
      <EmptyState v-else-if="sourcesAvailable === false" icon="⚠️" title="货源库暂不可用" description="当前无法确认货源记录；新增、编辑、删除和商品绑定均已禁用。">
        <AppButton :disabled="sourcesLoading" @click="loadSources">重试</AppButton>
      </EmptyState>
      <template v-else-if="sourcesAvailable === true">
      <BaseTable :columns="columns" :rows="rows" @row-click="selectSource">
        <template #title="{ row }">
          <div>
            <div class="strong">{{ row.title }}</div>
            <div class="subtle">{{ row.remark || '无备注' }}</div>
          </div>
        </template>
        <template #content="{ row }">
          <div class="content-preview">{{ row.content }}</div>
        </template>
        <template #usage="{ row }">
          <Badge>{{ row.usageCount || 0 }} 个商品</Badge>
        </template>
        <template #op="{ row }">
          <button class="link" :disabled="Boolean(mutationBusy)" @click.stop="editSource(row)">编辑</button>
          <button class="link" :disabled="detailLoading || analysisLoading || Boolean(mutationBusy)" @click.stop="analyzeSource(row)">AI 推荐</button>
          <button class="link danger-text" :disabled="Boolean(mutationBusy)" @click.stop="removeSource(row)">删除</button>
        </template>
      </BaseTable>
      <Pagination v-if="!mutationBusy" :total="sourceTotal" :current="query.current" :page-size="query.size" @page-change="goSourcePage" />
      </template>
    </CardPanel>

    <CardPanel v-if="editing" :title="editing.id ? '编辑货源' : '新增货源'" style="margin-top:16px">
      <div class="form-grid">
        <div class="form-row">
          <label>标题</label>
          <input v-model="form.title" class="input" maxlength="200" placeholder="给用户和 AI 模型看的标题" />
        </div>
        <div class="form-row">
          <label>正文</label>
          <textarea v-model="form.content" rows="6" placeholder="实际发货文本内容"></textarea>
        </div>
        <div class="form-row">
          <label>备注</label>
          <textarea v-model="form.remark" rows="3" maxlength="500" placeholder="可选备注"></textarea>
        </div>
      </div>
      <div class="toolbar" style="justify-content:flex-start">
        <AppButton type="primary" :disabled="sourcesAvailable !== true || Boolean(mutationBusy)" @click="saveSource">{{ mutationBusy === 'save' ? '保存中…' : '保存' }}</AppButton>
        <AppButton :disabled="mutationBusy === 'save'" @click="cancelEdit">取消</AppButton>
      </div>
    </CardPanel>

    <template v-if="selected">
      <CardPanel title="货源详情" style="margin-top:16px">
        <EmptyState v-if="detailLoading" icon="⏳" title="货源详情加载中" description="正在读取绑定商品，期间不会开放配置操作。" />
        <EmptyState v-else-if="detailAvailable === false" icon="⚠️" title="货源详情暂不可用" description="当前无法确认绑定关系；为避免把旧商品配置到新货源，所有写操作已禁用。">
          <AppButton :disabled="detailLoading" @click="loadSelectedGoods(selected.id, selected)">重试</AppButton>
        </EmptyState>
        <template v-else-if="detailAvailable === true">
        <div class="source-summary">
          <div class="summary-item">
            <div class="summary-label">当前货源</div>
            <div class="summary-value">{{ selected.title || '-' }}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">已配置商品</div>
            <div class="summary-value">{{ selected.usageCount || 0 }}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">可选商品总数</div>
            <div class="summary-value">{{ candidateLibraryTotal }}</div>
          </div>
        </div>
        <div class="subtle source-preview">{{ selected.content || '暂无正文内容' }}</div>
        </template>
      </CardPanel>

      <CardPanel v-if="detailAvailable === true" title="已配置商品" style="margin-top:16px">
        <div class="toolbar">
          <input
            v-model="configuredKeyword"
            class="input"
            placeholder="搜索已配置商品"
            style="max-width:260px"
            :disabled="detailLoading || Boolean(mutationBusy)"
            @keyup.enter="searchConfiguredGoods"
          />
          <AppButton :disabled="detailLoading || Boolean(mutationBusy)" @click="searchConfiguredGoods">搜索</AppButton>
          <AppButton :disabled="detailLoading || Boolean(mutationBusy)" @click="refreshSelectedGoods">刷新商品列表</AppButton>
        </div>
        <BaseTable :columns="configuredColumns" :rows="filteredConfiguredGoods">
          <template #title="{ row }">
            <div class="goods-cell">
              <img v-if="goodsCover(row)" :src="goodsCover(row)" class="goods-thumb" alt="" />
              <div v-else class="goods-thumb placeholder"></div>
              <div class="goods-main">
                <div class="strong">{{ row.title }}</div>
                <div class="subtle">{{ row.category || '-' }}</div>
                <div class="account-chip">
                  <img v-if="accountAvatar(row)" :src="accountAvatar(row)" class="account-avatar" alt="" />
                  <div v-else class="account-avatar placeholder avatar-placeholder"></div>
                  <span class="subtle">{{ accountDisplayLabel(row) }}</span>
                </div>
              </div>
            </div>
          </template>
          <template #bind="{ row }">
            <Badge type="green">{{ bindStateLabel(row) }}</Badge>
          </template>
          <template #single="{ row }">
            <button class="link" :disabled="detailLoading || analysisLoading || Boolean(mutationBusy)" @click.stop="applyOne(row)">再次配置</button>
            <button class="link danger-text" :disabled="detailLoading || analysisLoading || Boolean(mutationBusy)" @click.stop="removeConfiguredGoods(row)">删除</button>
          </template>
        </BaseTable>
        <Pagination
          v-if="!mutationBusy"
          :total="configuredGoodsPage.total"
          :current="configuredGoodsPage.current"
          :page-size="configuredGoodsPage.size"
          @page-change="goConfiguredGoodsPage"
        />
      </CardPanel>

      <CardPanel v-if="detailAvailable === true" :title="goodsView === 'recommend' ? 'AI 推荐商品' : '商品列表'" style="margin-top:16px">
        <div class="toolbar">
          <input
            v-model="goodsKeyword"
            class="input"
            placeholder="搜索商品标题 / 分类"
            style="max-width:260px"
            :disabled="detailLoading || Boolean(mutationBusy) || goodsView === 'recommend'"
            @keyup.enter="searchCandidateGoods"
          />
          <AppButton :disabled="detailLoading || Boolean(mutationBusy) || goodsView === 'recommend'" @click="searchCandidateGoods">搜索</AppButton>
          <AppButton :type="goodsView === 'all' ? 'primary' : 'default'" @click="showAllGoods">全部商品</AppButton>
          <AppButton type="primary" :disabled="detailLoading || analysisLoading || Boolean(mutationBusy)" @click="analyzeSource(selected)">AI 推荐商品</AppButton>
          <select v-model="applyTiming" class="input" style="max-width:200px">
            <option value="payDelivery">付款后发货</option>
            <option value="confirmDelivery">确认收货后赠送</option>
            <option value="reviewDelivery">好评后赠送</option>
          </select>
          <AppButton :disabled="selectedGoodsIds.length === 0 || detailAvailable !== true || Boolean(mutationBusy)" @click="applySelectedGoods">{{ mutationBusy === 'apply' ? '配置中…' : '批量配置' }}</AppButton>
        </div>
        <div v-if="!aiStatus.configured" class="ai-status-tip">
          {{ aiStatusMessage('未配置通用模型，当前仅展示规则匹配候选；完成模型配置后可使用 AI 推荐商品。') }}
        </div>
        <div class="subtle" style="margin-bottom:12px">
          {{ goodsView === 'recommend' ? recommendedHint : '可先查看全部商品，再使用 AI 自动筛选高匹配商品。' }}
        </div>
        <div
          v-if="goodsView === 'recommend' && recommendationPool.candidatePoolTruncated"
          class="ai-status-tip"
        >
          为控制 AI 成本与响应时间，本次仅在部分商品中分析（关键词匹配 + 最新 {{ recommendationPool.candidatePoolLimit }} 个，候选库共 {{ recommendationPool.candidatePoolTotal }} 个）。
        </div>
        <EmptyState
          v-if="goodsView === 'recommend' && analysisLoading && recommendationsAvailable !== true"
          icon="⏳"
          title="AI 推荐分析中"
          description="正在有界候选集中计算匹配结果，分析完成前不会开放配置操作。"
        />
        <EmptyState
          v-else-if="goodsView === 'recommend' && recommendationsAvailable === false"
          icon="⚠️"
          title="AI 推荐暂不可用"
          description="未能确认推荐结果，不会使用上一次结果执行批量配置。"
        >
          <AppButton :disabled="analysisLoading" @click="analyzeSource(selected)">重试</AppButton>
        </EmptyState>
        <BaseTable
          v-else
          v-model:selected-keys="pageSelectedGoodsIds"
          :columns="goodsColumns"
          :rows="filteredDisplayGoods"
          :selectable="true"
          :row-key="row => row.id"
        >
          <template #title="{ row }">
            <div class="goods-cell">
              <img v-if="goodsCover(row)" :src="goodsCover(row)" class="goods-thumb" alt="" />
              <div v-else class="goods-thumb placeholder"></div>
              <div class="goods-main">
                <div class="strong">{{ row.title }}</div>
                <div class="subtle">{{ row.category || '-' }}</div>
                <div class="account-chip">
                  <img v-if="accountAvatar(row)" :src="accountAvatar(row)" class="account-avatar" alt="" />
                  <div v-else class="account-avatar placeholder avatar-placeholder"></div>
                  <span class="subtle">{{ accountDisplayLabel(row) }}</span>
                </div>
              </div>
            </div>
          </template>
          <template #bind="{ row }">
            <Badge :type="row.configured ? 'green' : 'gray'">{{ bindStateLabel(row) }}</Badge>
          </template>
          <template #score="{ row }">
            <Badge :type="confidenceType(row.confidence, row.configured)">
              {{ confidenceLabel(row.confidence, row.configured) }}
            </Badge>
          </template>
          <template #reason="{ row }">
            <span class="subtle">{{ row.reason || (row.configured ? '该商品已配置当前货源' : '可手动配置') }}</span>
          </template>
          <template #single="{ row }">
            <button class="link" :disabled="detailLoading || analysisLoading || detailAvailable !== true || Boolean(mutationBusy)" @click.stop="applyOne(row)">{{ row.configured ? '重新配置' : '配置到该商品' }}</button>
          </template>
        </BaseTable>
        <Pagination
          v-if="!mutationBusy && goodsView === 'recommend'"
          :total="recommendedGoodsPage.total"
          :current="recommendedGoodsPage.current"
          :page-size="recommendedGoodsPage.size"
          @page-change="goRecommendedGoodsPage"
        />
        <Pagination
          v-else-if="!mutationBusy"
          :total="candidateGoodsPage.total"
          :current="candidateGoodsPage.current"
          :page-size="candidateGoodsPage.size"
          @page-change="goCandidateGoodsPage"
        />
      </CardPanel>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import CardPanel from '../components/CardPanel.vue'
import BaseTable from '../components/BaseTable.vue'
import AppButton from '../components/AppButton.vue'
import Badge from '../components/Badge.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import {
  applyDeliverySourceToGoods,
  createDeliverySource,
  deleteDeliverySource,
  getDeliverySourceGoods,
  getDeliverySources,
  recommendDeliverySourceGoods,
  removeDeliverySourceFromGoods,
  updateDeliverySource
} from '../api/autoDelivery.js'
import { getAiProviderStatus } from '../api/aiProvider.js'
import { recordsOf, totalOf } from '../utils/apiData.js'
import { confirmAction } from '../utils/confirmAction.js'
import { accountName } from '../utils/format.js'

const error = ref('')
const success = ref('')
const rows = ref([])
const sourceTotal = ref(0)
const sourcesAvailable = ref(null)
const sourcesLoading = ref(false)
const selected = ref(null)
const detailAvailable = ref(null)
const detailLoading = ref(false)
const analysisLoading = ref(false)
const mutationBusy = ref('')
let sourceRequestSequence = 0
let detailRequestSequence = 0
let recommendationRequestSequence = 0
const editing = ref(null)
const configuredGoods = ref([])
const allGoods = ref([])
const recommendedGoods = ref([])
const recommendedCandidateIds = ref([])
const candidateLibraryTotal = ref(0)
const selectedGoodsIds = ref([])
const applyTiming = ref('payDelivery')
const configuredKeyword = ref('')
const configuredAppliedKeyword = ref('')
const goodsKeyword = ref('')
const candidateAppliedKeyword = ref('')
const goodsView = ref('all')
const recommendationsAvailable = ref(null)
const aiStatus = ref({ configured: false, message: '' })
const SOURCE_LIBRARY_FOCUS_GOODS_KEY = 'xya:source-library-focus-goods-id'
const SOURCE_LIBRARY_FOCUS_TIMING_KEY = 'xya:source-library-focus-timing'
const focusedGoodsId = ref('')
const recommendedHint = ref('点击“AI 推荐商品”后，将展示适配度较高的商品。')

const configuredGoodsPage = reactive({ current: 1, size: 20, total: 0 })
const candidateGoodsPage = reactive({ current: 1, size: 20, total: 0 })
const recommendedGoodsPage = reactive({ current: 1, size: 20, total: 0 })
const recommendationPool = reactive({
  candidatePoolLimit: 200,
  candidatePoolSize: 0,
  candidatePoolTotal: 0,
  candidatePoolTruncated: false
})

const query = reactive({
  keyword: '',
  current: 1,
  size: 20
})

const form = reactive({
  title: '',
  content: '',
  remark: ''
})

const columns = [
  { key: 'title', title: '货源信息' },
  { key: 'content', title: '正文' },
  { key: 'usage', title: '已配置商品' },
  { key: 'op', title: '操作' }
]

const configuredColumns = [
  { key: 'title', title: '商品' },
  { key: 'bind', title: '状态' },
  { key: 'single', title: '操作' }
]

const goodsColumns = [
  { key: 'title', title: '商品' },
  { key: 'bind', title: '配置状态' },
  { key: 'score', title: '匹配度' },
  { key: 'reason', title: 'AI/规则理由' },
  { key: 'single', title: '操作' }
]

const configuredGoodsIds = computed(() => new Set(configuredGoods.value.map(row => String(row.id))))

const totalConfiguredCount = computed(() => {
  return rows.value.reduce((sum, row) => sum + (Number(row.usageCount) || 0), 0)
})

const normalizedConfiguredGoods = computed(() => decorateGoodsRows(configuredGoods.value, false))
const normalizedAllGoods = computed(() => decorateGoodsRows(allGoods.value, false))
const normalizedRecommendedGoods = computed(() => decorateGoodsRows(recommendedGoods.value, true))
const pagedRecommendedGoods = computed(() => {
  const offset = (recommendedGoodsPage.current - 1) * recommendedGoodsPage.size
  return normalizedRecommendedGoods.value.slice(offset, offset + recommendedGoodsPage.size)
})

const filteredConfiguredGoods = computed(() => normalizedConfiguredGoods.value)

const filteredDisplayGoods = computed(() => {
  return goodsView.value === 'recommend' ? pagedRecommendedGoods.value : normalizedAllGoods.value
})

const pageSelectedGoodsIds = computed({
  get: () => selectedGoodsIds.value,
  set: keys => {
    const visibleIds = new Set(filteredDisplayGoods.value.map(row => String(row.id)))
    const preserved = selectedGoodsIds.value.filter(id => !visibleIds.has(String(id)))
    const merged = [...preserved, ...(keys || [])]
    selectedGoodsIds.value = Array.from(
      new Map(merged.map(id => [String(id), id])).values()
    )
  }
})

function decorateGoodsRows(rows, fromAi) {
  return (rows || []).map(row => {
    const configured = Boolean(row.configured) || configuredGoodsIds.value.has(String(row.id))
    return {
      ...row,
      account: accountOf(row),
      configured,
      confidence: row.confidence || (configured ? 'medium' : 'low'),
      reason: row.reason || (configured ? '该商品已配置当前货源' : (fromAi ? 'AI 推荐商品' : '可手动配置')),
      recommended: fromAi || Boolean(row.recommended)
    }
  })
}

function accountOf(row) {
  return row?.account || {
    id: row?.accountId,
    avatarUrl: row?.accountAvatarUrl || '',
    nickname: row?.accountNickname || '',
    displayName: row?.accountDisplayName || '',
    accountNote: row?.accountRemark || '',
    externalUid: row?.accountExternalUid || ''
  }
}

function goodsCover(row) {
  return row?.coverPic || row?.imageUrl || ''
}

function accountAvatar(row) {
  return accountOf(row)?.avatarUrl || ''
}

function accountDisplayLabel(row) {
  const account = accountOf(row)
  const id = row?.accountId || account?.id
  const label = accountName(account || {})
  if (!id) {
    return label || '-'
  }
  return `${label || '账号'}（${id}）`
}

async function loadAiStatus() {
  try {
    const res = await getAiProviderStatus()
    aiStatus.value = res?.data || { configured: false, message: '' }
  } catch {
    if (import.meta.env.DEV) console.warn('[DeliverySourceLibrary] loadAiStatus failed')
    aiStatus.value = {
      configured: false,
      message: '未能读取 AI 模型配置状态，请稍后重试。'
    }
  }
}

function aiStatusMessage(defaultMessage = '未配置通用模型，请先前往系统设置中的“模型配置”完成配置。') {
  return aiStatus.value?.message || defaultMessage
}

function consumeFocusedContext() {
  focusedGoodsId.value = sessionStorage.getItem(SOURCE_LIBRARY_FOCUS_GOODS_KEY) || ''
  const timing = sessionStorage.getItem(SOURCE_LIBRARY_FOCUS_TIMING_KEY) || ''
  sessionStorage.removeItem(SOURCE_LIBRARY_FOCUS_GOODS_KEY)
  sessionStorage.removeItem(SOURCE_LIBRARY_FOCUS_TIMING_KEY)
  if (timing) {
    applyTiming.value = timing
  }
}

function applyFocusedGoodsContext(sourceRows = []) {
  if (!focusedGoodsId.value) return
  const target = sourceRows.find(row => String(row.id) === String(focusedGoodsId.value))
  if (!target) return
  if (!goodsKeyword.value) {
    goodsKeyword.value = target.title || String(target.id)
  }
  if (!target.configured) {
    selectedGoodsIds.value = [target.id]
  }
}

async function applyGoodsIds(goodsIds, successMessage, expectedSourceId = selected.value?.id) {
  const sourceId = expectedSourceId
  if (
    !sourceId
    || sourcesAvailable.value !== true
    || String(selected.value?.id) !== String(sourceId)
    || !goodsIds.length
    || detailAvailable.value !== true
    || mutationBusy.value
  ) return false
  const detailSequenceAtStart = detailRequestSequence
  mutationBusy.value = 'apply'
  try {
    await applyDeliverySourceToGoods(sourceId, {
      goodsIds,
      timing: applyTiming.value
    })
    success.value = successMessage
    selectedGoodsIds.value = []
    if (
      detailSequenceAtStart === detailRequestSequence
      && String(selected.value?.id) === String(sourceId)
    ) {
      await Promise.all([loadSelectedGoods(sourceId, selected.value), loadSources()])
    } else {
      await loadSources()
    }
    return true
  } finally {
    mutationBusy.value = ''
  }
}

async function loadSources() {
  const requestId = ++sourceRequestSequence
  error.value = ''
  sourcesLoading.value = true
  try {
    const res = await getDeliverySources(query)
    if (requestId !== sourceRequestSequence) return false
    rows.value = recordsOf(res.data)
    sourceTotal.value = totalOf(res.data, rows.value.length)
    sourcesAvailable.value = true
    if (selected.value?.id) {
      const latest = rows.value.find(row => String(row.id) === String(selected.value.id))
      if (latest) {
        selected.value = { ...selected.value, ...latest }
      } else {
        clearSelected()
      }
    }
    return true
  } catch (e) {
    if (requestId !== sourceRequestSequence) return false
    sourcesAvailable.value = false
    clearSelected()
    error.value = e.message || '货源库加载失败'
    return false
  } finally {
    if (requestId === sourceRequestSequence) sourcesLoading.value = false
  }
}

function searchSources() {
  if (mutationBusy.value) return
  query.current = 1
  loadSources()
}

function goSourcePage(page) {
  if (mutationBusy.value) return
  query.current = page
  loadSources()
}

function openCreate() {
  if (sourcesAvailable.value !== true || mutationBusy.value) return
  editing.value = {}
  Object.assign(form, { title: '', content: '', remark: '' })
}

function editSource(row) {
  if (sourcesAvailable.value !== true || mutationBusy.value) return
  editing.value = row
  Object.assign(form, {
    title: row.title || '',
    content: row.content || '',
    remark: row.remark || ''
  })
}

function cancelEdit() {
  editing.value = null
}

function clearSelected() {
  detailRequestSequence += 1
  recommendationRequestSequence += 1
  analysisLoading.value = false
  selected.value = null
  detailAvailable.value = null
  detailLoading.value = false
  configuredGoods.value = []
  allGoods.value = []
  recommendedGoods.value = []
  recommendedCandidateIds.value = []
  candidateLibraryTotal.value = 0
  selectedGoodsIds.value = []
  configuredKeyword.value = ''
  configuredAppliedKeyword.value = ''
  goodsKeyword.value = ''
  candidateAppliedKeyword.value = ''
  goodsView.value = 'all'
  recommendationsAvailable.value = null
  Object.assign(configuredGoodsPage, { current: 1, total: 0 })
  Object.assign(candidateGoodsPage, { current: 1, total: 0 })
  Object.assign(recommendedGoodsPage, { current: 1, total: 0 })
  Object.assign(recommendationPool, {
    candidatePoolSize: 0,
    candidatePoolTotal: 0,
    candidatePoolTruncated: false
  })
}

async function saveSource() {
  if (sourcesAvailable.value !== true || mutationBusy.value) return
  error.value = ''
  success.value = ''
  mutationBusy.value = 'save'
  try {
    const editingId = editing.value?.id
    if (editingId) {
      await updateDeliverySource(editingId, { ...form })
      success.value = '货源已更新'
    } else {
      await createDeliverySource({ ...form })
      success.value = '货源已新增'
    }
    editing.value = null
    await loadSources()
    if (editingId && String(selected.value?.id) === String(editingId)) {
      await loadSelectedGoods(editingId, selected.value)
    }
  } catch (e) {
    error.value = e.message || '保存失败'
  } finally {
    mutationBusy.value = ''
  }
}

async function removeSource(row) {
  if (sourcesAvailable.value !== true || mutationBusy.value) return
  mutationBusy.value = 'delete-confirm'
  try {
    if (!await confirmAction({
      title: '确认删除该货源？',
      description: '仅未被商品使用的货源可以删除；正在使用的货源会被服务端拒绝，以避免留下孤儿配置。',
      dangerous: true,
      confirmText: '删除'
    })) return
    mutationBusy.value = 'delete'
    await deleteDeliverySource(row.id)
    if (selected.value?.id === row.id) {
      clearSelected()
    }
    success.value = '货源已删除'
    await loadSources()
  } catch (e) {
    error.value = e.message || '删除失败'
  } finally {
    mutationBusy.value = ''
  }
}

function assignPageState(target, payload, fallbackRecords = []) {
  const page = payload || {}
  target.current = Number(page.current) || 1
  target.size = Number(page.size) || target.size
  target.total = totalOf(page, fallbackRecords.length)
  return recordsOf(page).length || Object.prototype.hasOwnProperty.call(page, 'records')
    ? recordsOf(page)
    : fallbackRecords
}

function detailPagingParams() {
  return {
    configuredCurrent: configuredGoodsPage.current,
    configuredSize: configuredGoodsPage.size,
    configuredKeyword: configuredAppliedKeyword.value,
    candidateCurrent: candidateGoodsPage.current,
    candidateSize: candidateGoodsPage.size,
    candidateKeyword: candidateAppliedKeyword.value
  }
}

function clearRecommendationState() {
  recommendationRequestSequence += 1
  analysisLoading.value = false
  recommendedGoods.value = []
  recommendedCandidateIds.value = []
  recommendationsAvailable.value = null
  goodsView.value = 'all'
  Object.assign(recommendedGoodsPage, { current: 1, total: 0 })
  Object.assign(recommendationPool, {
    candidatePoolSize: 0,
    candidatePoolTotal: 0,
    candidatePoolTruncated: false
  })
}

async function loadSelectedGoods(
  sourceId = selected.value?.id,
  candidate = selected.value,
  { resetPaging = false, clearRecommendation = true } = {}
) {
  if (!sourceId || sourcesAvailable.value !== true) return false
  const requestId = ++detailRequestSequence
  recommendationRequestSequence += 1
  analysisLoading.value = false
  selected.value = candidate || { id: sourceId }
  if (resetPaging) {
    configuredGoodsPage.current = 1
    candidateGoodsPage.current = 1
  }
  if (detailAvailable.value !== true || resetPaging) detailAvailable.value = null
  detailLoading.value = true
  if (resetPaging) {
    configuredGoods.value = []
    allGoods.value = []
    selectedGoodsIds.value = []
  }
  if (clearRecommendation) clearRecommendationState()
  try {
    const res = await getDeliverySourceGoods(sourceId, detailPagingParams())
    if (requestId !== detailRequestSequence) return false
    const data = res.data || {}
    selected.value = { ...(candidate || {}), ...(data.source || {}), id: sourceId }
    configuredGoods.value = assignPageState(
      configuredGoodsPage,
      data.configuredGoodsPage,
      data.configuredGoods || []
    )
    allGoods.value = assignPageState(
      candidateGoodsPage,
      data.allGoodsPage,
      data.allGoods || []
    )
    candidateLibraryTotal.value = Number(data.allGoodsTotal ?? candidateGoodsPage.total) || 0
    detailAvailable.value = true
    applyFocusedGoodsContext(normalizedAllGoods.value)
    return true
  } catch (e) {
    if (requestId !== detailRequestSequence) return false
    detailAvailable.value = false
    error.value = e.message || '货源详情与绑定商品加载失败'
    return false
  } finally {
    if (requestId === detailRequestSequence) detailLoading.value = false
  }
}

async function selectSource(row) {
  if (mutationBusy.value) return
  success.value = ''
  error.value = ''
  goodsView.value = 'all'
  configuredKeyword.value = ''
  configuredAppliedKeyword.value = ''
  goodsKeyword.value = ''
  candidateAppliedKeyword.value = ''
  await loadSelectedGoods(row.id, row, { resetPaging: true })
}

function recommendationParams() {
  return {
    candidateLimit: 200
  }
}

function applyRecommendationData(data, { replaceSelection = false } = {}) {
  aiStatus.value = {
    configured: data.configured !== false,
    message: data.message || aiStatus.value.message || ''
  }
  if (data.source) {
    selected.value = { ...(selected.value || {}), ...data.source }
  }
  recommendedGoods.value = data.candidates || []
  recommendedGoodsPage.current = 1
  recommendedGoodsPage.total = totalOf(data.candidatesPage, recommendedGoods.value.length)
  recommendedCandidateIds.value = data.applicableCandidateIds
    || normalizedRecommendedGoods.value.filter(row => !row.configured).map(row => row.id)
  const applicableIds = new Set(recommendedCandidateIds.value.map(id => String(id)))
  Object.assign(recommendationPool, {
    candidatePoolLimit: Number(data.candidatePoolLimit) || 200,
    candidatePoolSize: Number(data.candidatePoolSize) || 0,
    candidatePoolTotal: Number(data.candidatePoolTotal) || 0,
    candidatePoolTruncated: Boolean(data.candidatePoolTruncated)
  })
  recommendationsAvailable.value = true
  goodsView.value = 'recommend'
  recommendedHint.value = data.message || '已根据标题、正文和备注筛选出高适配商品。'
  if (replaceSelection) {
    selectedGoodsIds.value = [...recommendedCandidateIds.value]
    applyFocusedGoodsContext(normalizedRecommendedGoods.value)
  } else {
    selectedGoodsIds.value = selectedGoodsIds.value.filter(id => applicableIds.has(String(id)))
  }
}

async function requestRecommendation(sourceId, { replaceSelection = false } = {}) {
  const requestId = ++recommendationRequestSequence
  const analysisSequence = detailRequestSequence
  analysisLoading.value = true
  goodsView.value = 'recommend'
  if (!recommendedGoodsPage.total) recommendationsAvailable.value = null
  try {
    const res = await recommendDeliverySourceGoods(sourceId, recommendationParams())
    if (
      requestId !== recommendationRequestSequence
      || analysisSequence !== detailRequestSequence
      || String(selected.value?.id) !== String(sourceId)
    ) return false
    const data = res.data || {}
    applyRecommendationData(data, { replaceSelection })
    if (data.configured === false) {
      error.value = data.message || aiStatusMessage('未配置通用模型，暂时无法使用 AI 一键配置。')
      return false
    }
    if (data.errorCode === 'AI_ERROR') {
      error.value = data.message || 'AI 调用失败，已回退为规则匹配候选。'
      return false
    }
    if (!recommendedGoodsPage.total) {
      success.value = recommendedHint.value || '暂未匹配到适合的商品'
    }
    return true
  } catch (e) {
    if (requestId !== recommendationRequestSequence) return false
    recommendationsAvailable.value = false
    recommendedGoods.value = []
    recommendedCandidateIds.value = []
    selectedGoodsIds.value = []
    recommendedGoodsPage.total = 0
    error.value = e.message || 'AI 推荐加载失败'
    return false
  } finally {
    if (requestId === recommendationRequestSequence) analysisLoading.value = false
  }
}

async function analyzeSource(row) {
  if (
    !row
    || sourcesAvailable.value !== true
    || detailLoading.value
    || analysisLoading.value
    || mutationBusy.value
  ) return false
  error.value = ''
  success.value = ''
  const sourceId = row.id
  try {
    const switchingSource = String(selected.value?.id) !== String(sourceId)
    const loaded = await loadSelectedGoods(sourceId, row, { resetPaging: switchingSource })
    if (!loaded) return false
    recommendedGoodsPage.current = 1
    return await requestRecommendation(sourceId, { replaceSelection: true })
  } catch (e) {
    error.value = e.message || 'AI 配置失败'
    return false
  }
}

async function applySelectedGoods() {
  if (!selected.value || selectedGoodsIds.value.length === 0) return
  try {
    await applyGoodsIds(
      [...selectedGoodsIds.value],
      `已配置 ${selectedGoodsIds.value.length} 个商品`
    )
  } catch (e) {
    error.value = e.message || '批量配置失败'
  }
}

async function applyOne(row) {
  if (!selected.value) return
  try {
    await applyGoodsIds([row.id], '已配置到商品')
  } catch (e) {
    error.value = e.message || '配置失败'
  }
}

async function removeConfiguredGoods(row) {
  if (!selected.value?.id || detailLoading.value || analysisLoading.value || mutationBusy.value) return
  mutationBusy.value = 'delete-confirm'
  try {
    if (!await confirmAction({
      title: '确认删除该已配置商品？',
      description: '将解除该商品与当前货源的绑定，并停用对应的发货时机。商品本身不会被删除，可稍后重新配置。',
      dangerous: true,
      confirmText: '删除'
    })) return
    mutationBusy.value = 'remove-binding'
    const sourceId = selected.value.id
    await removeDeliverySourceFromGoods(sourceId, row.id)
    success.value = '已解除商品与货源的绑定'
    await Promise.all([loadSelectedGoods(sourceId, selected.value), loadSources()])
  } catch (e) {
    error.value = e.message || '删除失败'
  } finally {
    mutationBusy.value = ''
  }
}

async function refreshSelectedGoods() {
  error.value = ''
  if (!selected.value?.id || mutationBusy.value) return
  try {
    await Promise.all([loadSelectedGoods(selected.value.id), loadSources()])
  } catch (e) {
    error.value = e.message || '商品列表刷新失败'
  }
}

async function searchConfiguredGoods() {
  if (!selected.value?.id || detailLoading.value || mutationBusy.value) return
  configuredAppliedKeyword.value = configuredKeyword.value.trim()
  configuredGoodsPage.current = 1
  await loadSelectedGoods(selected.value.id, selected.value, { clearRecommendation: false })
}

async function searchCandidateGoods() {
  if (
    !selected.value?.id
    || detailLoading.value
    || mutationBusy.value
    || goodsView.value === 'recommend'
  ) return
  candidateAppliedKeyword.value = goodsKeyword.value.trim()
  candidateGoodsPage.current = 1
  selectedGoodsIds.value = []
  await loadSelectedGoods(selected.value.id, selected.value, { clearRecommendation: false })
}

async function goConfiguredGoodsPage(page) {
  if (!selected.value?.id || detailLoading.value || mutationBusy.value) return
  configuredGoodsPage.current = page
  await loadSelectedGoods(selected.value.id, selected.value, { clearRecommendation: false })
}

async function goCandidateGoodsPage(page) {
  if (!selected.value?.id || detailLoading.value || mutationBusy.value) return
  candidateGoodsPage.current = page
  await loadSelectedGoods(selected.value.id, selected.value, { clearRecommendation: false })
}

async function goRecommendedGoodsPage(page) {
  if (!selected.value?.id || analysisLoading.value || mutationBusy.value) return
  recommendedGoodsPage.current = page
}

function showAllGoods() {
  goodsView.value = 'all'
}

function confidenceLabel(confidence, configured) {
  if (configured) return '已配置'
  if (confidence === 'high') return '高度匹配'
  if (confidence === 'medium') return '中等匹配'
  return '待确认'
}

function confidenceType(confidence, configured) {
  if (configured) return 'green'
  if (confidence === 'high') return 'green'
  if (confidence === 'medium') return 'orange'
  return 'gray'
}

function bindStateLabel(row) {
  return row.configured ? '已配置' : '未配置'
}

function onHeaderAction(event) {
  if (event.detail === 'source-new') openCreate()
  if (event.detail === 'source-refresh' && !mutationBusy.value) {
    loadSources()
    refreshSelectedGoods()
  }
}

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  consumeFocusedContext()
  loadAiStatus()
  loadSources()
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-header-action', onHeaderAction)
})
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e8eef8;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(31,53,94,.04);
}
.stat-icon-circle {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}
.stat-icon-circle.blue { background: #e6f4ff; color: #0d6bff; }
.stat-icon-circle.green { background: #ecfdf3; color: #067647; }
.stat-icon-circle.orange { background: #fff7e6; color: #d97706; }
.stat-icon-circle.purple { background: #f3e8ff; color: #7c3aed; }
.stat-icon-circle.red { background: #fef2f2; color: #dc2626; }
.stat-icon-circle.gray { background: #f5f7fa; color: #64748b; }
.stat-info { min-width: 0; flex: 1; }
.stat-label {
  font-size: 12px;
  color: #667085;
  margin-bottom: 2px;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #15223a;
  line-height: 1.2;
}
.stat-trend {
  font-size: 11px;
  margin-top: 2px;
}
.stat-trend.muted { color: #94a3b8; }
.stat-trend.down { color: #dc2626; }

.content-preview {
  max-width: 520px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.strong {
  font-weight: 600;
}

.goods-cell {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 260px;
}

.goods-thumb {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  object-fit: cover;
  background: #eef2ff;
  flex-shrink: 0;
}

.goods-thumb.placeholder,
.account-avatar.placeholder {
  background: #eef2ff;
}

.goods-main {
  min-width: 0;
}

.account-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.account-avatar {
  width: 20px;
  height: 20px;
  border-radius: 999px;
  object-fit: cover;
  flex-shrink: 0;
}

.avatar-placeholder {
  position: relative;
}

.avatar-placeholder::before {
  content: '';
  position: absolute;
  inset: 5px;
  border-radius: 999px;
  background: #cbd5e1;
}

.source-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.summary-item {
  padding: 14px 16px;
  border: 1px solid #e7ecf3;
  border-radius: 12px;
  background: #f8fafc;
}

.summary-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}

.summary-value {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}

.source-preview {
  white-space: pre-wrap;
  line-height: 1.6;
}

.ai-status-tip {
  margin: 0 0 10px;
  padding: 10px 12px;
  border: 1px solid #fde68a;
  border-radius: 10px;
  background: #fffbeb;
  color: #b45309;
  font-size: 12px;
  line-height: 1.6;
}

/* ───── 移动端适配 ───── */
@media (max-width: 900px) {
  /* 统计网格：5 列 → 2 列堆叠 */
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }
  .stat-card {
    padding: 10px 12px;
    gap: 10px;
  }
  .stat-icon-circle {
    width: 34px;
    height: 34px;
    font-size: 16px;
  }
  .stat-value {
    font-size: 18px;
  }
  .stat-label {
    font-size: 11px;
  }
  .stat-trend {
    font-size: 10px;
  }

  /* 货源正文预览宽度收窄并允许换行 */
  .content-preview {
    max-width: 100%;
    white-space: normal;
    word-break: break-word;
  }

  /* 商品单元格最小宽度解除，允许更紧凑展示 */
  .goods-cell {
    min-width: 0;
    gap: 8px;
  }
  .goods-thumb {
    width: 40px;
    height: 40px;
    border-radius: 8px;
  }

  .account-chip {
    gap: 5px;
    margin-top: 4px;
  }
  .account-avatar {
    width: 18px;
    height: 18px;
  }

  /* 货源摘要：3列 → 单列堆叠 */
  .source-summary {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
    margin-bottom: 10px;
  }
  .source-summary > * {
    min-width: 0;
  }
  .summary-item {
    padding: 12px 14px;
  }
  .summary-label {
    font-size: 12px;
    margin-bottom: 4px;
  }
  .summary-value {
    font-size: 16px;
  }

  .source-preview {
    line-height: 1.5;
  }
}
</style>
