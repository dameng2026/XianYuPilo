<template>
  <div>
    <div v-if="error" class="global-notice error" role="alert">{{ error }}</div>
    <div v-if="warning" class="global-notice warning" role="status">{{ warning }}</div>
    <div v-if="success" class="global-notice success" role="status">{{ success }}</div>
    <div v-if="detailLoadError" class="global-notice error" role="alert">{{ detailLoadError }}</div>

    <CardPanel title="订单筛选">
      <div class="toolbar wrap">
        <select v-model="query.accountId" class="input select" :disabled="accountsAvailable === false" @change="search">
          <option value="">全部账号</option>
          <option v-for="account in accounts" :key="account.id" :value="String(account.id)">
            {{ accountName(account) }}
          </option>
        </select>
        <select v-model="query.status" class="input select" @change="search">
          <option value="">全部状态</option>
          <option value="0">待付款</option>
          <option value="1">已付款</option>
          <option value="2">待发货</option>
          <option value="3">已发货</option>
          <option value="4">已完成</option>
          <option value="5">已关闭</option>
        </select>
        <input v-model="query.keyword" class="input grow" placeholder="搜索订单号 / 买家 / 商品" @keyup.enter="search" />
        <AppButton type="primary" :loading="ordersLoading" @click="search">查询</AppButton>
        <AppButton @click="resetFilters">重置</AppButton>
        <AppButton :loading="syncingList" :disabled="!query.accountId" @click="syncAccountOrders">
          {{ syncingList ? '同步中...' : '同步当前账号真实订单' }}
        </AppButton>
      </div>
      <div class="sync-tip">
        选择账号后，列表查询会优先同步该账号的闲鱼真实订单，再展示当前筛选结果。
      </div>
    </CardPanel>

    <CardPanel title="订单列表" style="margin-top: 16px">
      <div v-if="ordersRefreshing" class="refresh-status" role="status" aria-live="polite">
        正在刷新订单列表，现有数据仍可查看。
      </div>
      <EmptyState v-if="ordersLoading && ordersAvailable !== true" icon="⏳" title="订单加载中" description="正在读取后端订单记录。" />
      <EmptyState v-else-if="ordersAvailable === false" icon="⚠️" title="订单列表暂不可用" description="当前无法确认是否存在订单，不会把查询失败显示为空列表。">
        <template #actions><AppButton @click="loadOrders">重新加载</AppButton></template>
      </EmptyState>
      <BaseTable v-else :columns="columns" :rows="rows" @row-click="selectOrder">
        <template #orderNo="{ row }">
          <div>
            <div class="strong">{{ row.externalOrderId || '-' }}</div>
            <div class="subtle">{{ row.createTimeText }}</div>
          </div>
        </template>
        <template #buyer="{ row }">
          <div>
            <div class="strong">{{ row.buyerName || '-' }}</div>
            <div class="subtle">{{ row.buyerId || '-' }}</div>
          </div>
        </template>
        <template #items="{ row }">
          <div class="goods-cell">
            <div v-for="(item, idx) in rowItemSlice(row)" :key="idx" class="goods-item">
              <img
                v-if="item.goodsImage && !failedImageUrls.has(item.goodsImage)"
                :src="item.goodsImage"
                class="goods-thumb"
                alt=""
                referrerpolicy="no-referrer"
                @error="onGoodsImageError($event, item)"
              />
              <div class="goods-info">
                <div class="goods-title">{{ item.goodsTitle || '-' }}<span v-if="item.externalGoodsId" class="goods-id-inline">（{{ item.externalGoodsId }}）</span></div>
              </div>
            </div>
            <div v-if="!rowItemSlice(row).length" class="subtle">{{ row.itemSummary }}</div>
          </div>
        </template>
        <template #quantity="{ row }">
          <div>
            <div class="strong">{{ row.quantityTotalText }}</div>
            <div class="subtle">{{ row.deliveryProgressText }}</div>
          </div>
        </template>
        <template #orderStatus="{ row }">
          <Badge :type="row.orderStatusBadge">{{ row.orderStatusText }}</Badge>
        </template>
        <template #delivery="{ row }">
          <div>
            <Badge :type="row.deliveryBadge">{{ row.deliveryStatusText }}</Badge>
            <div class="subtle" style="margin-top: 4px">{{ row.platformSyncTimeText }}</div>
          </div>
        </template>
        <template #op="{ row }">
          <div class="inline-actions">
            <button class="link" @click.stop="selectOrder(row)">查看详情</button>
            <button class="link" @click.stop="openManualDelivery(row)">手动发货</button>
            <button class="link" @click.stop="syncCurrentOrder(row)">
              {{ syncingOrderId === row.id ? '同步中...' : '同步' }}
            </button>
          </div>
        </template>
      </BaseTable>
      <Pagination v-if="ordersAvailable === true" :total="total" :current="query.current" :page-size="query.size" @page-change="goPage" />
    </CardPanel>

    <!-- 订单详情弹窗 -->
    <Teleport to="body">
      <div v-if="detailView" class="order-modal-mask" @click.self="closeDetail">
        <section class="order-modal">
          <button
            class="order-modal-close"
            :disabled="manualBusy"
            :title="manualBusy ? '发货执行中，暂不能关闭' : '关闭订单详情'"
            aria-label="关闭订单详情"
            @click="closeDetail"
          >
            <Icon name="close" />
          </button>
          <h2 class="order-modal-title">订单详情</h2>

          <div class="order-modal-body">
            <div class="detail-section">
              <div class="section-title">基本信息</div>
              <div class="detail-grid cols-2">
                <div class="detail-item"><span class="detail-label">订单ID</span><span class="detail-value mono">{{ detailView.externalOrderId || '-' }}</span></div>
                <div class="detail-item"><span class="detail-label">商品ID</span><span class="detail-value mono">{{ detailView.itemId || '-' }}</span></div>
                <div class="detail-item"><span class="detail-label">买家ID</span><span class="detail-value mono">{{ detailView.buyerId || '-' }}</span></div>
                <div class="detail-item"><span class="detail-label">买家昵称</span><span class="detail-value">{{ detailView.buyerName || '-' }}</span></div>
                <div class="detail-item"><span class="detail-label">所属账号</span><span class="detail-value">{{ accountLabel(detailView.accountId) }}</span></div>
                <div class="detail-item"><span class="detail-label">订单状态</span><span class="detail-value"><Badge :type="detailView.orderStatusBadge">{{ detailView.orderStatusText }}</Badge></span></div>
                <div class="detail-item"><span class="detail-label">是否小刀</span><span class="detail-value"><Badge :type="detailView.isBargainBadge">{{ detailView.isBargainText }}</Badge></span></div>
                <div class="detail-item"><span class="detail-label">已评价</span><span class="detail-value"><Badge :type="detailView.isRatedBadge">{{ detailView.isRatedText }}</Badge></span></div>
                <div class="detail-item"><span class="detail-label">求小红花</span><span class="detail-value"><Badge :type="detailView.isRedFlowerBadge">{{ detailView.isRedFlowerText }}</Badge></span></div>
              </div>
            </div>

            <div class="detail-section">
              <div class="section-title">发货信息</div>
              <div class="detail-grid cols-2">
                <div class="detail-item"><span class="detail-label">发货方式</span><span class="detail-value">{{ detailView.deliveryMethodText }}</span></div>
                <div class="detail-item"><span class="detail-label">发货状态</span><span class="detail-value"><Badge :type="detailView.deliveryBadge">{{ detailView.deliveryStatusText }}</Badge></span></div>
                <div class="detail-item"><span class="detail-label">发货进度</span><span class="detail-value">{{ detailView.deliveryProgressText }}</span></div>
                <div class="detail-item"><span class="detail-label">失败原因</span><span class="detail-value error-text">{{ detailView.deliveryFailReasonText }}</span></div>
              </div>
            </div>

            <div class="detail-section">
              <div class="section-title">时间信息</div>
              <div class="detail-grid cols-2">
                <div class="detail-item"><span class="detail-label">创建时间</span><span class="detail-value">{{ detailView.createTimeText }}</span></div>
                <div class="detail-item"><span class="detail-label">付款时间</span><span class="detail-value">{{ detailView.payTimeText || '-' }}</span></div>
                <div class="detail-item"><span class="detail-label">发货时间</span><span class="detail-value">{{ detailView.shipTimeText || '-' }}</span></div>
                <div class="detail-item"><span class="detail-label">最近同步</span><span class="detail-value">{{ detailView.platformSyncTimeText || '-' }}</span></div>
              </div>
            </div>

            <div class="detail-section">
              <div class="section-title">订单商品</div>
              <div v-if="detailView.itemLines.length" class="item-list">
                <div v-for="(line, index) in detailView.itemLines" :key="index" class="item-row">{{ line }}</div>
              </div>
              <div v-else class="subtle">当前还没有返回商品明细。</div>
            </div>

            <div class="detail-section">
              <div class="section-title">发货内容</div>
              <div class="content-box">{{ detailView.deliveryContent || '-' }}</div>
            </div>

            <!-- 手动发货表单（内嵌展开） -->
            <div v-if="manualForm.visible" class="manual-delivery-section">
              <div class="section-title">手动发货（立即执行）</div>
              <p class="manual-delivery-warning">
                确认后将立即向真实买家发送消息，并确认闲鱼平台发货。这不是定时或后台任务。
              </p>
              <div
                v-if="manualOutcome"
                :class="['manual-outcome', `is-${manualOutcome.tone}`]"
                :role="manualOutcome.tone === 'error' ? 'alert' : 'status'"
              >
                {{ manualOutcome.message }}
              </div>
              <div class="form-grid">
                <div class="form-field">
                  <label>发货方式</label>
                  <select v-model="manualForm.deliveryMode" class="input" :disabled="manualFieldsLocked || manualBusy">
                    <option value="text">文本发货</option>
                    <option value="card">卡密发货</option>
                  </select>
                </div>
                <div class="form-field">
                  <label>发货数量</label>
                  <input v-model="manualForm.quantityRequested" class="input" type="number" min="1" max="100" step="1" :disabled="manualFieldsLocked || manualBusy" />
                </div>
              </div>
              <div class="form-field">
                <label>发货内容</label>
                <textarea v-model="manualForm.deliveryContent" class="textarea" rows="5" maxlength="10000" placeholder="请输入发货文本、卡密内容或下载链接" :disabled="manualFieldsLocked || manualBusy"></textarea>
              </div>
              <div class="inline-actions">
                <AppButton type="primary" :loading="manualSubmitting" :disabled="manualSubmitDisabled" @click="submitManualDelivery">
                  {{ manualSubmitLabel }}
                </AppButton>
                <AppButton :disabled="manualBusy" @click="toggleManualDelivery(false)">取消</AppButton>
              </div>
            </div>

            <div v-if="!manualForm.visible" class="inline-actions" style="margin-top: 16px">
              <AppButton type="primary" :loading="syncingOrderId === detailView.id" @click="syncCurrentOrder(detailView)">
                {{ syncingOrderId === detailView.id ? '同步中...' : '同步当前订单' }}
              </AppButton>
              <AppButton @click="toggleManualDelivery(true)">手动发货</AppButton>
            </div>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import CardPanel from '../components/CardPanel.vue'
import BaseTable from '../components/BaseTable.vue'
import Badge from '../components/Badge.vue'
import AppButton from '../components/AppButton.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import Icon from '../components/Icon.vue'
import { getAccounts } from '../api/accounts.js'
import { getOrderDetail, getOrders, manualDeliverOrder, syncOrder, syncOrders } from '../api/orders.js'
import { recordsOf, totalOf } from '../utils/apiData.js'
import { confirmAction } from '../utils/confirmAction.js'
import { accountName } from '../utils/format.js'
import { createLatestRequestGuard, listRefreshRequestConfig } from '../utils/latestRequest.js'
import {
  buildManualDeliveryErrorOutcome,
  buildManualDeliveryOutcome,
  buildManualDeliveryPayload,
  buildPersistedManualDeliveryOutcome,
  buildOrderDetailViewModel,
  buildOrderRowViewModel,
  buildOrdersQuery,
  createManualDeliveryIdempotencyKey
} from '../utils/orderPageState.js'

const accounts = ref([])
const orders = ref([])
const selected = ref(null)
const total = ref(0)
const error = ref('')
const warning = ref('')
const success = ref('')
const detailLoadError = ref('')
const syncingList = ref(false)
const syncingOrderId = ref(null)
const manualSubmitting = ref(false)
const manualConfirming = ref(false)
const manualOutcome = ref(null)
const ordersLoading = ref(false)
const ordersAvailable = ref(null)
const accountsAvailable = ref(null)
const ordersRequestGuard = createLatestRequestGuard()

const query = reactive({
  accountId: '',
  status: '',
  keyword: '',
  current: 1,
  size: 20
})

const manualForm = reactive({
  visible: false,
  deliveryMode: 'text',
  deliveryContent: '',
  quantityRequested: 1,
  orderId: null,
  idempotencyKey: '',
  attemptVersion: ''
})

const columns = [
  { key: 'orderNo', title: '订单信息' },
  { key: 'buyer', title: '买家信息' },
  { key: 'items', title: '商品信息' },
  { key: 'quantity', title: '数量 / 进度' },
  { key: 'orderStatus', title: '订单状态' },
  { key: 'delivery', title: '发货状态' },
  { key: 'op', title: '操作' }
]

const rows = computed(() => orders.value.map(buildOrderRowViewModel))
const ordersRefreshing = computed(() => ordersLoading.value && ordersAvailable.value === true)
const detailView = computed(() => (selected.value ? buildOrderDetailViewModel(selected.value) : null))
const manualBusy = computed(() => manualConfirming.value || manualSubmitting.value)
const manualFieldsLocked = computed(() => manualOutcome.value !== null)
const manualSubmitDisabled = computed(() => manualBusy.value
  || (manualOutcome.value !== null && manualOutcome.value.retryAllowed !== true))
const manualSubmitLabel = computed(() => {
  if (manualConfirming.value) return '等待确认...'
  if (manualOutcome.value) return manualOutcome.value.submitLabel
  return '确认并立即发货'
})

function clearNotice() {
  error.value = ''
  warning.value = ''
  success.value = ''
  detailLoadError.value = ''
}

function appendWarning(message) {
  if (!message) return
  warning.value = warning.value ? `${warning.value} ${message}` : message
}

function showManualOutcome(outcome) {
  error.value = ''
  warning.value = ''
  success.value = ''
  if (outcome.tone === 'success') success.value = outcome.message
  else if (outcome.tone === 'error') error.value = outcome.message
  else warning.value = outcome.message
}

function accountLabel(accountId) {
  const match = accounts.value.find(item => String(item.id) === String(accountId))
  return match ? accountName(match) : '-'
}

function rowItemSlice(row) {
  const items = Array.isArray(row?.items) ? row.items : []
  return items.slice(0, 2)
}

// 记录加载失败的图片 URL，避免污染原数据（切换页码再回来时可重新尝试）
const failedImageUrls = reactive(new Set())
function onGoodsImageError(event, item) {
  // 封面图加载失败时记录 URL，仅显示文字（不修改原数据）
  if (item?.goodsImage) failedImageUrls.add(item.goodsImage)
  if (event?.target) event.target.style.display = 'none'
}

async function loadOrders(options = {}) {
  const request = ordersRequestGuard.begin()
  const hadSnapshot = ordersAvailable.value === true
  const hadAccountSnapshot = accountsAvailable.value === true
  const keepSelectedId = options.keepSelectedId ?? selected.value?.id
  const sync = options.sync
  const silent = options.silent === true
  if (!silent) clearNotice()
  if (!silent) ordersLoading.value = true
  const requestConfig = listRefreshRequestConfig(hadSnapshot)
  try {
    const [accountResult, orderResult] = await Promise.allSettled([
      getAccounts({ page: 1, pageSize: 200 }, requestConfig),
      getOrders(buildOrdersQuery({ ...query, sync }), requestConfig)
    ])
    if (!request.isCurrent()) return
    if (accountResult.status === 'fulfilled') {
      accounts.value = recordsOf(accountResult.value.data)
      accountsAvailable.value = true
    } else if (!hadAccountSnapshot) {
      accounts.value = []
      accountsAvailable.value = false
      appendWarning('账号筛选暂不可用；已加载订单仍可查看，但账号名称可能无法解析。')
    } else {
      appendWarning('账号筛选刷新失败，继续使用上次成功加载的账号选项。')
    }
    if (orderResult.status === 'fulfilled' && orderResult.value?.data) {
      orders.value = recordsOf(orderResult.value.data)
      total.value = totalOf(orderResult.value.data, orders.value.length)
      ordersAvailable.value = true
      if (keepSelectedId && !orders.value.some(item => String(item.id) === String(keepSelectedId))) {
        selected.value = null
        manualForm.visible = false
      }
    } else if (!hadSnapshot) {
      orders.value = []
      total.value = 0
      ordersAvailable.value = false
      selected.value = null
      manualForm.visible = false
      error.value = orderResult.status === 'rejected'
        ? (orderResult.reason?.message || '加载订单列表失败')
        : '订单列表响应无效，请稍后重试'
    } else {
      const message = orderResult.status === 'rejected'
        ? orderResult.reason?.message
        : '订单列表响应无效'
      appendWarning(`订单列表刷新失败，继续显示上次成功加载的订单数据。${message ? ` ${message}` : ''}`)
    }
  } catch (requestError) {
    if (!request.isCurrent()) return
    if (hadSnapshot) {
      appendWarning(`订单列表刷新失败，继续显示上次成功加载的订单数据。${requestError.message ? ` ${requestError.message}` : ''}`)
    } else {
      orders.value = []
      total.value = 0
      ordersAvailable.value = false
      selected.value = null
      manualForm.visible = false
      error.value = requestError.message || '加载订单列表失败'
    }
  } finally {
    if (request.isCurrent()) ordersLoading.value = false
  }
}

async function selectOrder(row) {
  clearNotice()
  detailLoadError.value = ''
  selected.value = null
  manualForm.visible = false
  if (ordersAvailable.value === false) {
    detailLoadError.value = '订单列表不可用，请先刷新列表'
    return false
  }
  try {
    const res = await getOrderDetail(row.id)
    if (!res?.data || typeof res.data !== 'object' || Array.isArray(res.data)
      || String(res.data.id ?? '') !== String(row.id)) {
      throw new Error('订单详情响应格式异常')
    }
    selected.value = res.data
    return true
  } catch (requestError) {
    detailLoadError.value = requestError?.message || '加载订单详情失败'
    return false
  }
}

function closeDetail() {
  if (manualBusy.value) return
  selected.value = null
  manualForm.visible = false
}

function primeManualForm() {
  const order = selected.value || {}
  const orderChanged = String(manualForm.orderId ?? '') !== String(order.id ?? '')
  const initializeForm = orderChanged || !manualForm.idempotencyKey
  const attempt = order.manualDeliveryAttempt
  const attemptVersion = attempt
    ? `${attempt.attemptId || ''}:${attempt.status || ''}:${attempt.updatedTime || ''}`
    : ''
  if (initializeForm) {
    manualForm.orderId = order.id ?? null
    manualForm.idempotencyKey = createManualDeliveryIdempotencyKey()
    manualForm.deliveryMode = order.deliveryMethod === 'manual_card' ? 'card' : 'text'
    manualForm.deliveryContent = order.deliveryContent || ''
    manualForm.quantityRequested = Number(order.quantityRequested ?? order.quantityTotal ?? 1) || 1
  }
  if (initializeForm || attemptVersion !== manualForm.attemptVersion) {
    if (!initializeForm && attempt) {
      manualForm.deliveryMode = order.deliveryMethod === 'manual_card' ? 'card' : 'text'
      manualForm.deliveryContent = order.deliveryContent || ''
      manualForm.quantityRequested = Number(order.quantityRequested ?? order.quantityTotal ?? 1) || 1
    }
    manualForm.attemptVersion = attemptVersion
    manualOutcome.value = buildPersistedManualDeliveryOutcome(attempt)
  }
}

async function openManualDelivery(row) {
  if (!selected.value || String(selected.value.id) !== String(row.id)) {
    if (!await selectOrder(row)) return
  }
  primeManualForm()
  manualForm.visible = true
}

function toggleManualDelivery(visible) {
  if (!visible) {
    if (manualBusy.value) return
    manualForm.visible = false
    return
  }
  primeManualForm()
  manualForm.visible = true
}

async function refreshSelectedOrder() {
  if (!selected.value?.id) return
  await selectOrder(selected.value)
}

async function submitManualDelivery() {
  if (!selected.value?.id || manualBusy.value || manualSubmitDisabled.value) return
  if (!manualForm.idempotencyKey) {
    manualForm.idempotencyKey = createManualDeliveryIdempotencyKey()
  }
  const requestedQuantity = Number(manualForm.quantityRequested)
  if (!Number.isInteger(requestedQuantity) || requestedQuantity < 1 || requestedQuantity > 100) {
    clearNotice()
    error.value = '发货数量必须是 1 到 100 之间的整数'
    return
  }
  const payload = buildManualDeliveryPayload(manualForm)
  if (!payload.deliveryContent) {
    clearNotice()
    error.value = '请先填写发货内容'
    return
  }

  const onlyConfirmPlatform = manualOutcome.value?.retryScope === 'platform_confirm'
  manualConfirming.value = true
  let confirmed
  try {
    confirmed = await confirmAction({
      title: onlyConfirmPlatform ? '确认仅重试平台发货？' : '确认立即手动发货？',
      description: onlyConfirmPlatform
        ? '买家消息已经发送。本次只重试确认闲鱼平台发货，绝不会再次向买家发送消息。'
        : '确认后将立即向真实买家发送消息，并确认闲鱼平台发货。请再次核对发货内容和数量。',
      confirmText: onlyConfirmPlatform ? '仅确认平台发货' : '立即发货',
      dangerous: true
    })
  } finally {
    manualConfirming.value = false
  }
  if (!confirmed) return

  clearNotice()
  manualSubmitting.value = true
  try {
    const res = await manualDeliverOrder(selected.value.id, payload)
    const outcome = buildManualDeliveryOutcome(res?.data || {})
    manualOutcome.value = outcome
    if (outcome.status === 'success') {
      manualForm.visible = false
      manualForm.idempotencyKey = ''
      manualForm.orderId = null
      manualForm.attemptVersion = ''
    }
    await loadOrders({ keepSelectedId: selected.value.id, sync: false })
    await refreshSelectedOrder()
    showManualOutcome(outcome)
  } catch (requestError) {
    const outcome = buildManualDeliveryErrorOutcome(requestError)
    manualOutcome.value = outcome
    showManualOutcome(outcome)
  } finally {
    manualSubmitting.value = false
  }
}

async function syncCurrentOrder(row) {
  clearNotice()
  syncingOrderId.value = row.id
  try {
    const res = await syncOrder(row.id)
    const data = res?.data
    if (!data || typeof data !== 'object' || Array.isArray(data) || typeof data.ok !== 'boolean') {
      throw new Error('订单同步结果响应格式异常')
    }
    await loadOrders({ keepSelectedId: row.id, sync: false })
    if (selected.value && String(selected.value.id) === String(row.id)) {
      await refreshSelectedOrder()
    }
    if (data.ok) success.value = data.message || '订单同步已完成'
    else error.value = data.message || '订单同步失败'
  } catch (requestError) {
    error.value = requestError.message || '提交订单同步失败'
  } finally {
    syncingOrderId.value = null
  }
}

async function syncAccountOrders() {
  if (!query.accountId) {
    error.value = '请先选择要同步的账号'
    return
  }
  clearNotice()
  syncingList.value = true
  try {
    const res = await syncOrders({
      accountId: Number(query.accountId),
      syncDeliveryStatus: true
    })
    const data = res?.data
    if (!data || typeof data !== 'object' || Array.isArray(data) || typeof data.ok !== 'boolean') {
      throw new Error('账号订单同步结果响应格式异常')
    }
    await loadOrders({ sync: false })
    if (data.ok === false) error.value = data.message || '账号订单同步失败'
    else success.value = data.message || '账号真实订单同步已完成'
  } catch (requestError) {
    error.value = requestError.message || '提交账号订单同步失败'
  } finally {
    syncingList.value = false
  }
}

function search() {
  query.current = 1
  loadOrders()
}

function resetFilters() {
  query.accountId = ''
  query.status = ''
  query.keyword = ''
  query.current = 1
  selected.value = null
  manualForm.visible = false
  loadOrders({ keepSelectedId: null })
}

function goPage(page) {
  query.current = page
  loadOrders()
}

function onHeaderAction(event) {
  if (event.detail === 'orders-refresh') loadOrders()
}

let ordersPollTimer = null
let ordersPollVisible = true

function startOrdersPolling() {
  if (ordersPollTimer) return
  ordersPollTimer = setInterval(() => {
    if (!ordersPollVisible || document.hidden) return
    if (ordersLoading.value || syncingList.value) return
    loadOrders({ sync: false, silent: true })
  }, 30000)
}

function stopOrdersPolling() {
  if (ordersPollTimer) {
    clearInterval(ordersPollTimer)
    ordersPollTimer = null
  }
}

function onVisibilityChange() {
  ordersPollVisible = !document.hidden
  if (ordersPollVisible) {
    loadOrders({ sync: false, silent: true })
  }
}

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  document.addEventListener('visibilitychange', onVisibilityChange)
  loadOrders()
  startOrdersPolling()
})

onBeforeUnmount(() => {
  ordersRequestGuard.invalidate()
  window.removeEventListener('xya-header-action', onHeaderAction)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopOrdersPolling()
})
</script>

<style scoped>
/* 订单详情弹窗 */
.order-modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 36, 58, .58);
  backdrop-filter: blur(2px);
  z-index: 1001;
  display: flex;
  align-items: center;
  justify-content: center;
}

.order-modal {
  position: relative;
  width: 720px;
  max-width: 92vw;
  max-height: 85vh;
  background: #fff;
  border: 1px solid #e8eef8;
  border-radius: 18px;
  box-shadow: 0 28px 80px rgba(17, 35, 67, .25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.order-modal-close {
  position: absolute;
  right: 16px;
  top: 14px;
  width: 32px;
  height: 32px;
  border: 0;
  background: transparent;
  color: #35435d;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 1;
}

.order-modal-close .ui-icon {
  width: 20px;
}

.order-modal-close:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.order-modal-title {
  margin: 0;
  padding: 20px 24px 12px;
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  border-bottom: 1px solid #f0f3f8;
}

.order-modal-body {
  padding: 20px 24px 24px;
  overflow-y: auto;
  flex: 1;
}

.manual-delivery-section {
  margin-top: 16px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px solid #e8eef8;
}

.manual-delivery-warning {
  margin: 8px 0 14px;
  padding: 10px 12px;
  border: 1px solid #f7c97a;
  border-radius: 8px;
  background: #fff8e8;
  color: #8a4b08;
  font-size: 13px;
  line-height: 1.6;
}

.manual-outcome {
  margin: 0 0 14px;
  padding: 10px 12px;
  border: 1px solid #f7c97a;
  border-radius: 8px;
  background: #fff8e8;
  color: #8a4b08;
  font-size: 13px;
  line-height: 1.6;
}

.manual-outcome.is-success {
  border-color: #abefc6;
  background: #ecfdf3;
  color: #067647;
}

.manual-outcome.is-error {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b42318;
}

.wrap {
  flex-wrap: wrap;
}

.select {
  max-width: 220px;
}

.grow {
  flex: 1 1 240px;
}

.sync-tip {
  margin-top: 10px;
  color: #6b7a90;
  font-size: 12px;
  line-height: 1.6;
}

.refresh-status {
  margin-bottom: 10px;
  color: #526079;
  font-size: 13px;
}

.goods-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.goods-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.goods-thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #e6ecf5;
  background: #f5f7fa;
  flex-shrink: 0;
}

.goods-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.goods-title {
  font-size: 13px;
  color: #2a3142;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.goods-id-inline {
  font-size: 12px;
  color: #8893a7;
  font-weight: normal;
}

.goods-id {
  font-size: 11px;
  color: #8893a7;
  line-height: 1.2;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-grid {
  display: grid;
  gap: 0;
}

.detail-grid.cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.detail-item {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f0f3f8;
  min-height: 36px;
}

.detail-label {
  color: #6b7a90;
  font-size: 13px;
  min-width: 80px;
  flex-shrink: 0;
}

.detail-value {
  color: #1e293b;
  font-size: 13px;
  font-weight: 500;
}

.detail-value.mono {
  font-family: "SF Mono", Monaco, "Cascadia Code", Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
}

.detail-value .error-text {
  color: #dc2626;
}

.section-title {
  margin-bottom: 4px;
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}

.item-list {
  display: grid;
  gap: 8px;
}

.item-row {
  padding: 10px 12px;
  border: 1px solid #e6ecf5;
  border-radius: 10px;
  background: #f8fbff;
}

.content-box {
  min-height: 64px;
  padding: 12px;
  border: 1px solid #e6ecf5;
  border-radius: 10px;
  background: #fbfdff;
  white-space: pre-wrap;
  word-break: break-word;
}

.inline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.form-field {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
}

.textarea {
  width: 100%;
  min-height: 120px;
  padding: 10px 12px;
  border: 1px solid #d9e2f0;
  border-radius: 10px;
  resize: vertical;
}

.strong {
  font-weight: 600;
}

.success {
  background: #ecfdf3;
  color: #067647;
  border-color: #abefc6;
}

.warning {
  background: #fff8e8;
  color: #8a4b08;
  border-color: #f7c97a;
}

/* ───── 移动端适配 ───── */
@media (max-width: 900px) {
  /* 订单详情弹窗：全宽底部弹出 */
  .order-modal-mask {
    align-items: flex-end;
  }
  .order-modal {
    width: 100vw;
    max-width: 100vw;
    max-height: 90vh;
    border-radius: 20px 20px 0 0;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }
  .order-modal-close {
    right: 12px;
    top: 10px;
    width: 36px;
    height: 36px;
  }
  .order-modal-title {
    padding: 14px 14px 10px;
    font-size: 18px;
  }
  .order-modal-body {
    padding: 12px 14px 16px;
  }

  /* 手动发货区块内边距收窄 */
  .manual-delivery-section {
    margin-top: 12px;
    padding: 12px;
    border-radius: 10px;
  }

  /* 工具栏筛选元素全宽堆叠 */
  .select {
    max-width: 100%;
    width: 100%;
  }
  .grow {
    flex: 1 1 100%;
    width: 100%;
  }

  /* 商品缩略图与标题缩窄 */
  .goods-thumb {
    width: 36px;
    height: 36px;
  }
  .goods-title {
    font-size: 13px;
    max-width: 160px;
  }

  /* 详情双列网格 → 单列堆叠 */
  .detail-grid.cols-2 {
    grid-template-columns: minmax(0, 1fr);
  }
  .detail-item {
    padding: 8px 0;
    min-height: 32px;
  }
  .detail-label {
    min-width: 72px;
    font-size: 13px;
  }
  .detail-value {
    font-size: 13px;
  }

  .detail-section {
    margin-bottom: 14px;
  }
  .section-title {
    font-size: 14px;
  }

  /* 表单三列 → 单列 */
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }
  /* 网格子元素防止溢出 */
  .detail-grid.cols-2 > *,
  .form-grid > * {
    min-width: 0;
  }
  .form-field {
    gap: 6px;
    margin-bottom: 10px;
  }
  .textarea {
    min-height: 100px;
  }

  /* 商品条目与内容框内边距收窄 */
  .item-row {
    padding: 8px 10px;
  }
  .content-box {
    min-height: 56px;
    padding: 10px;
  }

  .inline-actions {
    gap: 8px;
  }
}
</style>
