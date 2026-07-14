<template>
  <div class="m-products">
    <div class="m-page-header">
      <h1>商品管理</h1>
      <p class="m-page-sub">商品列表与状态查看</p>
    </div>

    <div class="m-prod-actions">
      <label class="m-prod-search">
        <MIcon name="search" :size="16" />
        <input v-model.trim="keyword" type="search" placeholder="搜索商品名称或 ID" aria-label="搜索商品" @keyup.enter="runSearch" />
      </label>
      <button class="m-prod-refresh" :disabled="loading" @click="loadProducts()">
        <MIcon name="refresh" :size="16" />
        <span>{{ loading ? '加载中' : '刷新' }}</span>
      </button>
    </div>

    <div v-if="error" class="m-data-warning" role="alert">
      <span>{{ error }}</span>
      <button type="button" @click="loadProducts()">重试</button>
    </div>
    <div v-if="accountsError" class="m-data-warning" role="status">{{ accountsError }}</div>

    <div class="m-prod-stats">
      <div class="m-prod-stat-card">
        <div class="m-prod-stat-icon m-prod-stat-icon-blue">
          <MIcon name="bag" :size="20" />
        </div>
        <div class="m-prod-stat-info">
          <div class="m-prod-stat-val">{{ statsAvailable ? stats.total : '—' }}</div>
          <div class="m-prod-stat-label">商品总数</div>
        </div>
      </div>
      <div class="m-prod-stat-card">
        <div class="m-prod-stat-icon m-prod-stat-icon-green">
          <MIcon name="check" :size="20" />
        </div>
        <div class="m-prod-stat-info">
          <div class="m-prod-stat-val">{{ statsAvailable ? stats.onSale : '—' }}</div>
          <div class="m-prod-stat-label">在售</div>
        </div>
      </div>
      <div class="m-prod-stat-card">
        <div class="m-prod-stat-icon m-prod-stat-icon-orange">
          <MIcon name="box" :size="20" />
        </div>
        <div class="m-prod-stat-info">
          <div class="m-prod-stat-val">{{ statsAvailable ? stats.offShelf : '—' }}</div>
          <div class="m-prod-stat-label">下架</div>
        </div>
      </div>
      <div class="m-prod-stat-card">
        <div class="m-prod-stat-icon m-prod-stat-icon-green">
          <MIcon name="truck" :size="20" />
        </div>
        <div class="m-prod-stat-info">
          <div class="m-prod-stat-val">{{ statsAvailable ? stats.deliveryConfigured : '—' }}</div>
          <div class="m-prod-stat-label">已配置发货</div>
        </div>
      </div>
    </div>

    <div class="m-prod-filter">
      <div class="m-prod-filter-scroll">
        <button
          class="m-prod-chip"
          :class="{ 'm-prod-chip-active': selectedAccountId === null }"
          @click="selectAccount(null)"
        >
          <MIcon name="bag" :size="14" />
          <span>全部账号</span>
        </button>
        <button
          v-for="acc in accounts"
          :key="acc.id"
          class="m-prod-chip"
          :class="{ 'm-prod-chip-active': selectedAccountId === acc.id }"
          @click="selectAccount(acc.id)"
        >
          {{ acc.nickname || acc.remark || acc.username || `账号${acc.id}` }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="m-loading">加载中...</div>

    <div v-else-if="listAvailable && products.length === 0" class="m-empty">
      <div class="m-empty-icon">
        <MIcon name="bag" :size="48" />
      </div>
      <div class="m-empty-text">暂无商品</div>
      <div class="m-empty-desc">当账号同步商品后会在这里显示</div>
      <button class="m-empty-btn" @click="loadProducts()">
        <MIcon name="refresh" :size="14" />
        <span>重新加载</span>
      </button>
    </div>

    <div v-else class="m-prod-list">
      <div v-for="prod in products" :key="prod.id || prod.itemId" class="m-prod-card">
        <div class="m-prod-card-top">
          <div class="m-prod-cover">
            <img
              v-if="prod.coverPic"
              :src="prod.coverPic"
              :alt="prod.name"
              class="m-prod-img"
              @error="onImgError($event, prod)"
            />
            <div v-else class="m-prod-cover-placeholder">
              <MIcon name="bag" :size="28" />
            </div>
          </div>
          <div class="m-prod-body">
            <div class="m-prod-name">{{ prod.name || '未命名商品' }}</div>
            <div class="m-prod-price-row">
              <span class="m-prod-price">{{ formatPrice(prod.price) }}</span>
              <span class="m-prod-status" :class="statusClass(prod.statusCode)">
                {{ statusText(prod.statusCode) }}
              </span>
            </div>
            <div class="m-prod-meta">
              <span class="m-prod-stock">
                <MIcon name="box" :size="11" />
                库存 {{ prod.stock != null ? prod.stock : '—' }}
              </span>
              <span
                class="m-prod-delivery"
                :class="prod.deliveryOn ? 'm-prod-delivery-on' : 'm-prod-delivery-off'"
              >
                <MIcon name="truck" :size="11" />
                {{ prod.deliveryOn ? '已配置发货' : '未配置发货' }}
              </span>
            </div>
          </div>
        </div>
        <div class="m-prod-card-stats">
          <div class="m-prod-stat-item">
            <MIcon name="eye" :size="12" />
            <span class="m-prod-stat-num">{{ prod.exposureCount ?? '—' }}</span>
            <span class="m-prod-stat-text">曝光</span>
          </div>
          <div class="m-prod-stat-item">
            <MIcon name="chart" :size="12" />
            <span class="m-prod-stat-num">{{ prod.viewCount ?? '—' }}</span>
            <span class="m-prod-stat-text">浏览</span>
          </div>
          <div class="m-prod-stat-item">
            <MIcon name="heart" :size="12" />
            <span class="m-prod-stat-num">{{ prod.wantCount ?? '—' }}</span>
            <span class="m-prod-stat-text">想要</span>
          </div>
        </div>
      </div>
    </div>

    <button v-if="listAvailable && products.length < total" class="m-load-more" :disabled="loading" @click="loadMore">
      {{ loading ? '加载中...' : `加载更多（${products.length}/${total}）` }}
    </button>

    <div class="m-prod-tip">
      <MIcon name="warning" :size="16" />
      <span>商品发布、编辑等复杂操作建议在PC端完成</span>
      <button class="m-tip-btn" @click="$emit('force-desktop')">进入桌面版</button>
    </div>

    <div class="m-safe-bottom"></div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import MIcon from './MIcon.vue'
import { getGoods, getGoodsStats } from '../api/goods.js'
import { getAccounts } from '../api/accounts.js'
import { recordsOf } from '../utils/apiData.js'

defineEmits(['navigate', 'force-desktop', 'back'])

const products = ref([])
const accounts = ref([])
const selectedAccountId = ref(null)
const loading = ref(true)
const keyword = ref('')
const page = ref(1)
const total = ref(0)
const listAvailable = ref(false)
const statsAvailable = ref(false)
const error = ref('')
const accountsError = ref('')
const stats = ref({ total: 0, onSale: 0, offShelf: 0, deliveryConfigured: 0 })

async function loadAccounts() {
  accountsError.value = ''
  try {
    const res = await getAccounts({ page: 1, pageSize: 100 })
    if (res?.data?.records) {
      accounts.value = res.data.records
    } else if (Array.isArray(res?.data)) {
      accounts.value = res.data
    }
  } catch {
    accounts.value = []
    accountsError.value = '账号筛选暂不可用；商品列表仍可按全部账号加载。'
  }
}

async function loadProducts({ append = false } = {}) {
  if (loading.value && append) return
  loading.value = true
  error.value = ''
  if (!append) page.value = 1
  const params = { page: page.value, pageSize: 50 }
  if (selectedAccountId.value != null) params.xianyuAccountId = selectedAccountId.value
  if (keyword.value) params.keyword = keyword.value
  const [listResult, statsResult] = await Promise.allSettled([
    getGoods(params),
    getGoodsStats(selectedAccountId.value == null ? {} : { xianyuAccountId: selectedAccountId.value })
  ])
  const failures = []
  if (listResult.status === 'fulfilled' && listResult.value?.data) {
    const data = listResult.value.data
    const nextRecords = recordsOf(data)
    products.value = append ? [...products.value, ...nextRecords] : nextRecords
    total.value = Number(data.total ?? products.value.length)
    listAvailable.value = true
  } else {
    if (!append) products.value = []
    listAvailable.value = false
    failures.push('商品列表')
  }
  if (statsResult.status === 'fulfilled' && statsResult.value?.data) {
    const data = statsResult.value.data
    stats.value = {
      total: Number(data.total ?? 0),
      onSale: Number(data.onSale ?? 0),
      offShelf: Number(data.offShelfOrDraft ?? 0),
      deliveryConfigured: Number(data.autoDeliveryOn ?? 0)
    }
    statsAvailable.value = true
  } else {
    statsAvailable.value = false
    failures.push('商品统计')
  }
  if (failures.length) error.value = `${failures.join('、')}暂不可用；失败区域不会显示为零。`
  loading.value = false
}

function selectAccount(id) {
  if (selectedAccountId.value === id) return
  selectedAccountId.value = id
  loadProducts()
}

function runSearch() {
  loadProducts()
}

function loadMore() {
  if (loading.value || products.value.length >= total.value) return
  page.value += 1
  loadProducts({ append: true })
}

function formatPrice(price) {
  if (price == null || price === '') return '价格未知'
  const num = Number(price)
  if (isNaN(num)) return '价格未知'
  return `¥${Number.isInteger(num) ? String(num) : num.toFixed(2)}`
}

function statusText(code) {
  const value = Number(code)
  if (value === 1) return '在售'
  if (value === 3) return '已删除'
  if (value === 0) return '下架'
  return '未知'
}

function statusClass(code) {
  const value = Number(code)
  if (value === 1) return 'm-prod-status-on'
  if (value === 3) return 'm-prod-status-del'
  if (value === 0) return 'm-prod-status-off'
  return 'm-prod-status-off'
}

function onImgError(e, prod) {
  prod.coverPic = ''
}

onMounted(async () => {
  await loadAccounts()
  await loadProducts()
})
</script>

<style scoped>
.m-products {
  padding: 12px 16px 0;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  overflow-x: hidden;
}
.m-page-header { margin-bottom: 16px; }
.m-page-header h1 { margin: 0 0 4px; font-size: 26px; font-weight: 800; color: #15213d; }
.m-page-sub { margin: 0; font-size: 13px; color: #8c98ae; }

.m-prod-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.m-prod-search {
  flex: 1;
  min-width: 0;
  height: 36px;
  background: white;
  border: 1px solid #f0f4fa;
  border-radius: 100px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  color: #8c98ae;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
}
.m-prod-search :deep(svg) { color: #b0bacb; flex-shrink: 0; }
.m-prod-search input {
  width: 100%; min-width: 0; border: none; outline: none; background: transparent;
  color: #15213d; font-size: 13px;
}
.m-prod-refresh {
  flex-shrink: 0;
  height: 36px;
  padding: 0 14px;
  background: white;
  border: 1px solid #f0f4fa;
  border-radius: 100px;
  color: #5a6a85;
  font-size: 13px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
  transition: all 0.15s;
}
.m-prod-refresh:active { transform: scale(0.96); }
.m-prod-refresh :deep(svg) { color: #0d6bff; flex-shrink: 0; }
.m-prod-refresh:disabled { opacity: 0.65; cursor: wait; }

.m-data-warning {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-bottom: 12px; padding: 12px 14px; border: 1px solid #f6d58a;
  border-radius: 14px; color: #8a4b08; background: #fff8e8;
  font-size: 12px; line-height: 1.5;
}
.m-data-warning button {
  min-height: 40px; padding: 0 14px; flex-shrink: 0; border: 1px solid #e2ad3b;
  border-radius: 12px; color: #744006; background: white; font-weight: 600;
}

.m-prod-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}
.m-prod-stat-card {
  background: white;
  border-radius: 16px;
  padding: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
  border: 1px solid #f0f4fa;
}
.m-prod-stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.m-prod-stat-icon-blue {
  background: linear-gradient(135deg, #e8f1ff, #d4e4ff);
  color: #0d6bff;
}
.m-prod-stat-icon-green {
  background: linear-gradient(135deg, #e2f8ee, #cdf2df);
  color: #16bf78;
}
.m-prod-stat-icon-orange {
  background: linear-gradient(135deg, #fff4e0, #ffe7c2);
  color: #ff9f22;
}
.m-prod-stat-info { flex: 1; min-width: 0; }
.m-prod-stat-val { font-size: 22px; font-weight: 800; color: #15213d; line-height: 1.1; }
.m-prod-stat-label { font-size: 12px; color: #8c98ae; margin-top: 3px; }

.m-prod-filter {
  margin-bottom: 14px;
  margin-left: -16px;
  margin-right: -16px;
  padding-left: 16px;
  padding-right: 16px;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.m-prod-filter::-webkit-scrollbar { display: none; }
.m-prod-filter-scroll {
  display: inline-flex;
  gap: 8px;
  white-space: nowrap;
}
.m-prod-chip {
  flex-shrink: 0;
  height: 36px;
  background: white;
  border: 1px solid #e0e6f0;
  color: #5a6a85;
  padding: 0 14px;
  border-radius: 100px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.m-prod-chip :deep(svg) { flex-shrink: 0; }
.m-prod-chip:active { transform: scale(0.96); }
.m-prod-chip-active {
  background: linear-gradient(135deg, #0d6bff, #2580ff);
  color: white;
  border-color: transparent;
  box-shadow: 0 4px 12px rgba(13, 107, 255, 0.25);
}

.m-loading { text-align: center; padding: 40px; color: #8c98ae; font-size: 14px; }

.m-empty {
  text-align: center;
  padding: 60px 20px;
}
.m-empty-icon {
  width: 96px;
  height: 96px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e8f1ff, #d4e4ff);
  color: #0d6bff;
  display: flex;
  align-items: center;
  justify-content: center;
}
.m-empty-text { font-size: 16px; font-weight: 600; color: #15213d; margin-bottom: 6px; }
.m-empty-desc { font-size: 13px; color: #8c98ae; margin-bottom: 16px; }
.m-empty-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: linear-gradient(135deg, #0d6bff, #2580ff);
  color: white;
  border: none;
  border-radius: 100px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(13, 107, 255, 0.25);
}
.m-empty-btn :deep(svg) { flex-shrink: 0; }
.m-load-more {
  width: 100%; min-height: 44px; margin-top: 12px; border: 1px solid #d7e5fb;
  border-radius: 14px; color: #0d6bff; background: #f5f9ff; font-weight: 600;
  cursor: pointer;
}
.m-load-more:disabled { opacity: 0.65; cursor: wait; }

.m-prod-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.m-prod-card {
  background: white;
  border-radius: 16px;
  padding: 12px;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
  border: 1px solid #f0f4fa;
  max-width: 100%;
  overflow: hidden;
}
.m-prod-card-top {
  display: flex;
  gap: 10px;
  min-width: 0;
}
.m-prod-cover {
  width: 80px;
  height: 80px;
  border-radius: 12px;
  overflow: hidden;
  flex-shrink: 0;
  background: #f4f7fc;
}
.m-prod-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.m-prod-cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b0bacb;
  background: linear-gradient(135deg, #f4f7fc, #eaf0fa);
}
.m-prod-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  overflow: hidden;
}
.m-prod-name {
  font-size: 14px;
  font-weight: 700;
  color: #15213d;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}
.m-prod-price-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.m-prod-price {
  font-size: 16px;
  font-weight: 800;
  color: #ff5b2e;
}
.m-prod-status {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 100px;
  flex-shrink: 0;
}
.m-prod-status-on {
  background: rgba(22, 191, 120, 0.12);
  color: #16bf78;
}
.m-prod-status-off {
  background: rgba(255, 159, 34, 0.12);
  color: #ff9f22;
}
.m-prod-status-del {
  background: rgba(140, 152, 174, 0.15);
  color: #8c98ae;
}
.m-prod-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.m-prod-stock {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: #8c98ae;
}
.m-prod-stock :deep(svg) { flex-shrink: 0; }
.m-prod-delivery {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 100px;
  font-weight: 600;
}
.m-prod-delivery :deep(svg) { flex-shrink: 0; }
.m-prod-delivery-on {
  background: rgba(22, 191, 120, 0.1);
  color: #16bf78;
}
.m-prod-delivery-off {
  background: rgba(255, 159, 34, 0.1);
  color: #ff9f22;
}

.m-prod-card-stats {
  display: flex;
  align-items: center;
  justify-content: space-around;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #f4f7fc;
}
.m-prod-stat-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #8c98ae;
}
.m-prod-stat-item :deep(svg) { color: #b0bacb; flex-shrink: 0; }
.m-prod-stat-num {
  font-size: 13px;
  font-weight: 700;
  color: #5a6a85;
}
.m-prod-stat-text { font-size: 11px; }

.m-prod-tip {
  margin-top: 20px;
  background: #f8faff;
  border-radius: 14px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #72809a;
}
.m-prod-tip :deep(svg) { color: #ff9f22; flex-shrink: 0; }
.m-tip-btn {
  margin-left: auto;
  background: linear-gradient(135deg, #0d6bff, #2580ff);
  color: white;
  border: none;
  border-radius: 100px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
}

.m-safe-bottom { height: 80px; }
</style>
