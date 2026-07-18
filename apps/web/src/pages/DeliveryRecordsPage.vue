<template>
  <div>
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="warning" class="global-notice warning" role="status">{{ warning }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>
    <div class="global-notice capability-notice" role="status">
      当前版本没有安全的发货记录自动重试执行器。请先在闲鱼 App 核对买家消息与平台发货状态；确需再次操作时，请前往“订单管理”使用手动发货闭环。
    </div>

    <CardPanel title="发货记录筛选">
      <div class="toolbar wrap">
        <select v-model="query.status" class="input narrow">
          <option value="">全部状态</option>
          <option value="0">待处理</option>
          <option value="1">进行中</option>
          <option value="2">成功</option>
          <option value="3">失败</option>
          <option value="6">缺货</option>
          <option value="7">配置错误</option>
        </select>
        <select v-model="query.timing" class="input narrow">
          <option value="">全部时机</option>
          <option value="after_payment">付款后</option>
          <option value="after_receipt">收货后</option>
          <option value="after_review">评价后</option>
        </select>
        <select v-model="query.deliveryMode" class="input narrow">
          <option value="">全部方式</option>
          <option value="text">文本</option>
          <option value="card">卡密</option>
        </select>
        <input v-model="query.goodsKeyword" class="input grow" placeholder="商品关键词" />
        <input v-model="query.buyerKeyword" class="input grow" placeholder="买家关键词" />
        <input v-model="query.orderKeyword" class="input grow" placeholder="订单号 / 外部订单号" />
        <AppButton type="primary" :loading="recordsLoading" @click="search">搜索</AppButton>
        <AppButton @click="resetFilters">重置</AppButton>
        <AppButton :disabled="recordsAvailable !== true || exportLoading" @click="exportCsv">
          {{ exportLoading ? '导出中...' : '导出 CSV' }}
        </AppButton>
      </div>
    </CardPanel>

    <CardPanel title="发货记录" style="margin-top: 16px">
      <div v-if="recordsRefreshing" class="refresh-status" role="status" aria-live="polite">
        正在刷新发货记录，现有数据仍可查看。
      </div>
      <EmptyState
        v-if="recordsLoading && recordsAvailable !== true"
        icon="⏳"
        title="正在加载发货记录"
        description="正在读取实际发货执行结果，请稍候。"
      />
      <EmptyState
        v-else-if="recordsAvailable === false"
        icon="⚠️"
        title="发货记录暂不可用"
        description="当前无法确认发货记录与执行结果；请求失败不会显示为空记录。"
      >
        <template #actions><AppButton @click="load">重新加载</AppButton></template>
      </EmptyState>
      <BaseTable
        v-else-if="recordsAvailable === true"
        :columns="columns"
        :rows="rows"
        :row-key="row => row.id"
        @row-click="showDetail"
      >
        <template #goods="{ row }">
          <div class="goods-cell">
            <img
              v-if="row.goodsCoverPic"
              :src="row.goodsCoverPic"
              alt=""
              loading="lazy"
              referrerpolicy="no-referrer"
              class="goods-thumb"
              @error="onGoodsThumbError(row, $event)"
            />
            <span class="cell-ellipsis" :title="row.goodsTitleText">{{ row.goodsTitleText }}</span>
          </div>
        </template>
        <template #status="{ row }">
          <Badge :type="row.deliveryBadge">{{ row.deliveryStatusText }}</Badge>
        </template>
        <template #timing="{ row }">
          {{ row.timingText }}
        </template>
        <template #mode="{ row }">
          {{ row.deliveryModeText }}
        </template>
        <template #progress="{ row }">
          {{ row.deliveryProgressText }}
        </template>
        <template #errorMessage="{ row }">
          <span class="cell-ellipsis" :title="row.errorMessage || ''">{{ row.errorMessage || '-' }}</span>
        </template>
        <template #op="{ row }">
          <div class="inline-actions">
            <button class="link" @click.stop="showDetail(row)">详情</button>
          </div>
        </template>
      </BaseTable>
      <Pagination v-if="recordsAvailable === true" :total="total" :current="query.current" :page-size="query.size" @page-change="goPage" />
    </CardPanel>

    <CardPanel v-if="detailView" title="发货记录详情" style="margin-top: 16px">
      <div class="detail-grid">
        <div><b>记录 ID：</b> {{ detailView.id || '-' }}</div>
        <div><b>订单号：</b> {{ detailView.orderId || '-' }}</div>
        <div><b>外部订单号：</b> {{ detailView.externalOrderId || '-' }}</div>
        <div><b>商品：</b> {{ detailView.goodsTitleText }}</div>
        <div><b>商品 ID：</b> {{ detailView.goodsId || '-' }}</div>
        <div><b>买家：</b> {{ detailView.buyerNameText }}</div>
        <div><b>卖家：</b> {{ detailView.sellerNameText }}</div>
        <div><b>购买时间：</b> {{ detailView.purchaseTimeText || '-' }}</div>
        <div><b>状态：</b> {{ detailView.deliveryStatusText }}</div>
        <div><b>进度：</b> {{ detailView.deliveryProgressText }}</div>
        <div><b>时机：</b> {{ detailView.timingText }}</div>
        <div><b>方式：</b> {{ detailView.deliveryModeText }}</div>
        <div><b>创建时间：</b> {{ detailView.createdTimeText }}</div>
        <div><b>完成时间：</b> {{ detailView.completedTimeText }}</div>
        <div><b>平台同步：</b> {{ detailView.platformSyncTimeText }}</div>
        <div><b>结果：</b> {{ detailView.resultText }}</div>
      </div>

      <div class="panel-block">
        <div class="section-title">发货内容</div>
        <div class="content-box">{{ detailView.deliveryContentText }}</div>
      </div>

      <div class="panel-block">
        <div class="section-title">错误信息</div>
        <div class="content-box">{{ detailView.errorMessageText }}</div>
      </div>
    </CardPanel>
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
import { getDeliveryRecordDetail, getDeliveryRecords } from '../api/autoDelivery.js'
import { camelizeKeys, recordsOf, recordsOfOrThrow, totalOf } from '../utils/apiData.js'
import { createLatestRequestGuard, listRefreshRequestConfig } from '../utils/latestRequest.js'
import {
  buildDeliveryRecordDetailViewModel,
  buildDeliveryRecordRowViewModel
} from '../utils/deliveryRecordsPageState.js'

const records = ref([])
const total = ref(0)
const detail = ref(null)
const error = ref('')
const warning = ref('')
const success = ref('')
const recordsAvailable = ref(null)
const recordsLoading = ref(true)
const exportLoading = ref(false)
const recordsRequestGuard = createLatestRequestGuard()

const query = reactive({
  status: '',
  timing: '',
  deliveryMode: '',
  goodsKeyword: '',
  buyerKeyword: '',
  orderKeyword: '',
  current: 1,
  size: 20
})

const columns = [
  { key: 'id', title: 'ID' },
  { key: 'orderId', title: '订单号' },
  { key: 'goods', title: '商品' },
  { key: 'buyerNameText', title: '买家' },
  { key: 'sellerNameText', title: '卖家' },
  { key: 'timing', title: '时机' },
  { key: 'mode', title: '方式' },
  { key: 'status', title: '状态' },
  { key: 'progress', title: '进度' },
  { key: 'errorMessage', title: '错误' },
  { key: 'purchaseTimeText', title: '购买时间' },
  { key: 'createdTimeText', title: '创建时间' },
  { key: 'op', title: '操作' }
]

const rows = computed(() => records.value.map(buildDeliveryRecordRowViewModel))
const recordsRefreshing = computed(() => recordsLoading.value && recordsAvailable.value === true)
const detailView = computed(() => (detail.value ? buildDeliveryRecordDetailViewModel(detail.value) : null))

function onGoodsThumbError(_row, event) {
  if (event?.target) event.target.style.display = 'none'
}

function clearNotice() {
  error.value = ''
  warning.value = ''
  success.value = ''
}

function buildQuery() {
  return {
    status: query.status === '' ? undefined : Number(query.status),
    timing: query.timing || undefined,
    deliveryMode: query.deliveryMode || undefined,
    goodsKeyword: query.goodsKeyword || undefined,
    buyerKeyword: query.buyerKeyword || undefined,
    orderKeyword: query.orderKeyword || undefined,
    current: query.current,
    size: query.size
  }
}

async function load() {
  const request = recordsRequestGuard.begin()
  const hadSnapshot = recordsAvailable.value === true
  clearNotice()
  recordsLoading.value = true
  try {
    const res = await getDeliveryRecords(buildQuery(), listRefreshRequestConfig(hadSnapshot))
    if (!request.isCurrent()) return
    records.value = camelizeKeys(recordsOfOrThrow(res.data, '发货记录响应格式异常'))
    total.value = totalOf(res.data, records.value.length)
    recordsAvailable.value = true
  } catch (requestError) {
    if (!request.isCurrent()) return
    if (hadSnapshot) {
      warning.value = `发货记录刷新失败，继续显示上次成功加载的发货记录。${requestError.message ? ` ${requestError.message}` : ''}`
    } else {
      records.value = []
      total.value = 0
      detail.value = null
      recordsAvailable.value = false
      error.value = requestError.message || '加载发货记录失败'
    }
  } finally {
    if (request.isCurrent()) recordsLoading.value = false
  }
}

async function showDetail(row) {
  clearNotice()
  detail.value = null
  try {
    const res = await getDeliveryRecordDetail(row.id)
    if (!res.data) throw new Error('发货记录详情响应为空')
    detail.value = camelizeKeys(res.data)
  } catch (requestError) {
    detail.value = null
    error.value = requestError.message || '加载发货记录详情失败'
  }
}


function search() {
  query.current = 1
  load()
}

function resetFilters() {
  query.status = ''
  query.timing = ''
  query.deliveryMode = ''
  query.goodsKeyword = ''
  query.buyerKeyword = ''
  query.orderKeyword = ''
  query.current = 1
  load()
}

function goPage(page) {
  query.current = page
  load()
}

function escapeCsv(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

async function exportCsv() {
  if (recordsAvailable.value !== true || exportLoading.value) {
    error.value = '发货记录尚不可用，请重新加载成功后再导出。'
    return
  }
  clearNotice()
  exportLoading.value = true
  const EXPORT_MAX_LIMIT = 2000   // 单次导出最大条数，防止浏览器内存压力
  const EXPORT_PAGE_SIZE = 100    // 分页拉取每页大小（后端 PageUtils 限制 max=100）
  const totalCount = total.value || 0
  if (totalCount > EXPORT_MAX_LIMIT) {
    error.value = `当前共 ${totalCount} 条记录，超过单次导出上限 ${EXPORT_MAX_LIMIT} 条，请添加筛选条件缩小范围后再导出`
    exportLoading.value = false
    return
  }
  try {
    success.value = '正在准备导出数据...'
    const exportRows = []
    // 总数为 0 时也尝试拉取一页（可能 total 尚未加载）
    const targetCount = Math.max(totalCount, query.size)
    const totalPages = Math.max(1, Math.ceil(targetCount / EXPORT_PAGE_SIZE))
    for (let page = 1; page <= totalPages; page++) {
      const res = await getDeliveryRecords({
        ...buildQuery(),
        current: page,
        size: EXPORT_PAGE_SIZE
      })
      const pageRecords = camelizeKeys(recordsOf(res.data)).map(buildDeliveryRecordRowViewModel)
      exportRows.push(...pageRecords)
      if (pageRecords.length < EXPORT_PAGE_SIZE) break  // 已到末页
      if (exportRows.length >= EXPORT_MAX_LIMIT) {
        exportRows.length = EXPORT_MAX_LIMIT
        break
      }
      success.value = `正在导出 ${exportRows.length} / ${targetCount} 条...`
    }
    if (!exportRows.length) {
      success.value = ''
      error.value = '没有可导出的发货记录'
      return
    }

    const headers = ['ID', '订单号', '商品', '买家', '时机', '方式', '状态', '进度', '错误', '创建时间']
    const lines = [
      headers.join(','),
      ...exportRows.map(row => ([
        row.id,
        row.orderId,
        row.goodsTitleText,
        row.buyerNameText,
        row.timingText,
        row.deliveryModeText,
        row.deliveryStatusText,
        row.deliveryProgressText,
        row.errorMessage || '',
        row.createdTimeText
      ]).map(escapeCsv).join(','))
    ]

    const blob = new Blob(['\uFEFF' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `delivery-records-${Date.now()}.csv`
    link.click()
    URL.revokeObjectURL(url)
    success.value = `已导出 ${exportRows.length} 条发货记录`
  } catch (requestError) {
    success.value = ''
    error.value = requestError.message || '导出发货记录失败'
  } finally {
    exportLoading.value = false
  }
}

function onHeaderAction(event) {
  if (event.detail === 'delivery-records-refresh') load()
  if (event.detail === 'delivery-records-export') exportCsv()
}

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  load()
})

onBeforeUnmount(() => {
  recordsRequestGuard.invalidate()
  window.removeEventListener('xya-header-action', onHeaderAction)
})
</script>

<style scoped>
.wrap {
  flex-wrap: wrap;
}

.narrow {
  max-width: 160px;
}

.grow {
  flex: 1 1 180px;
}

.refresh-status {
  margin-bottom: 10px;
  color: #526079;
  font-size: 13px;
}

.warning {
  background: #fff8e8;
  color: #8a4b08;
  border-color: #f7c97a;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}

.panel-block {
  margin-top: 16px;
}

.section-title {
  margin-bottom: 8px;
  font-weight: 600;
}

.content-box {
  min-height: 56px;
  padding: 12px;
  border: 1px solid #e6ecf5;
  border-radius: 10px;
  background: #fbfdff;
  white-space: pre-wrap;
  word-break: break-word;
}

.content-box.compact {
  min-height: auto;
}

.cell-ellipsis {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.form-field {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
}

.success {
  background: #ecfdf3;
  color: #067647;
  border-color: #abefc6;
}

/* ───── 移动端适配 ───── */
@media (max-width: 900px) {
  /* 筛选工具栏：narrow / grow 全宽堆叠 */
  .narrow {
    max-width: 100%;
    width: 100%;
  }
  .grow {
    flex: 1 1 100%;
    width: 100%;
  }

  /* 详情双列网格 → 单列堆叠 */
  .detail-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }
  .detail-grid > * {
    min-width: 0;
  }

  /* 面板间距收窄 */
  .panel-block {
    margin-top: 12px;
  }
  .section-title {
    margin-bottom: 6px;
  }

  /* 内容框内边距收窄 */
  .content-box {
    min-height: 48px;
    padding: 10px;
  }

  /* 错误信息省略宽度收窄 */
  .cell-ellipsis {
    max-width: 140px;
  }

  .inline-actions {
    gap: 8px;
  }

  .form-field {
    gap: 6px;
    margin-bottom: 10px;
  }
}
.goods-cell { display: flex; align-items: center; gap: 8px; min-width: 120px; }
.goods-thumb { width: 40px; height: 40px; object-fit: cover; border-radius: 6px; flex-shrink: 0; }
</style>
