<template>
  <div class="m-accounts">
    <div class="m-page-header">
      <h1>闲鱼账号</h1>
      <p class="m-page-sub">管理监控账号状态</p>
    </div>

    <div v-if="error" class="m-state-warning" role="alert">
      <span>{{ error }}</span>
      <button type="button" @click="loadAccounts">重试</button>
    </div>

    <div class="m-acc-stats">
      <div class="m-acc-stat-card">
        <div class="m-acc-stat-icon m-acc-stat-icon-blue">
          <MIcon name="account" :size="20" />
        </div>
        <div class="m-acc-stat-info">
          <div class="m-acc-stat-val">{{ summaryAvailable ? stats.total : '—' }}</div>
          <div class="m-acc-stat-label">账号总数</div>
        </div>
      </div>
      <div class="m-acc-stat-card">
        <div class="m-acc-stat-icon m-acc-stat-icon-green">
          <MIcon name="wifi" :size="20" />
        </div>
        <div class="m-acc-stat-info">
          <div class="m-acc-stat-val">{{ summaryAvailable ? stats.online : '—' }}</div>
          <div class="m-acc-stat-label">WS 在线</div>
        </div>
      </div>
      <div class="m-acc-stat-card">
        <div class="m-acc-stat-icon m-acc-stat-icon-gray">
          <MIcon name="account" :size="20" />
        </div>
        <div class="m-acc-stat-info">
          <div class="m-acc-stat-val">{{ summaryAvailable ? stats.normal : '—' }}</div>
          <div class="m-acc-stat-label">认证正常</div>
        </div>
      </div>
      <div class="m-acc-stat-card">
        <div class="m-acc-stat-icon m-acc-stat-icon-red">
          <MIcon name="warning" :size="20" />
        </div>
        <div class="m-acc-stat-info">
          <div class="m-acc-stat-val">{{ summaryAvailable ? stats.abnormal : '—' }}</div>
          <div class="m-acc-stat-label">认证异常</div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="m-loading">加载中...</div>

    <div v-else-if="dataAvailable && accounts.length === 0" class="m-empty">
      <div class="m-empty-icon">
        <MIcon name="account" :size="48" />
      </div>
      <div class="m-empty-text">暂无账号</div>
      <div class="m-empty-desc">添加闲鱼账号后将在这里显示</div>
    </div>

    <div v-else-if="dataAvailable" class="m-acc-list">
      <div v-for="acc in accounts" :key="acc.id" class="m-acc-card">
        <!-- 顶部：头像 + 名称 + 状态 -->
        <div class="m-acc-card-header">
          <div class="m-acc-avatar-wrap">
            <div class="m-acc-avatar">
              <img
                v-if="acc.avatarUrl || acc.avatar"
                :src="acc.avatarUrl || acc.avatar"
                :alt="accountName(acc)"
                class="m-acc-avatar-img"
                @error="onAvatarError($event, acc)"
              />
              <div v-else class="m-acc-avatar-placeholder">
                <MIcon name="user" :size="24" />
              </div>
            </div>
            <span
              class="m-acc-status-dot"
              :class="wsStatusClass(acc, 'dot')"
            ></span>
          </div>
          <div class="m-acc-card-title">
            <div class="m-acc-name">{{ accountName(acc) }}</div>
            <div class="m-acc-sub">
              <span v-if="accountLevel(acc) && accountLevel(acc) !== '-'" class="m-acc-level">
                <MIcon name="star" :size="10" />
                Lv{{ accountLevel(acc) }}
              </span>
              <span class="m-acc-uid">UID {{ acc.uid || acc.externalUid || acc.unb || acc.id || '-' }}</span>
            </div>
          </div>
          <span class="m-acc-status-pill" :class="wsStatusClass(acc, 'pill')">
            {{ wsStatusText(acc) }}
          </span>
        </div>

        <!-- 核心指标：大号数字，一目了然 -->
        <div class="m-acc-metrics">
          <div class="m-acc-metric">
            <div class="m-acc-metric-val">{{ acc.orderCount ?? '—' }}</div>
            <div class="m-acc-metric-label">订单</div>
          </div>
          <div class="m-acc-metric-divider"></div>
          <div class="m-acc-metric">
            <div class="m-acc-metric-val">{{ acc.productCount ?? '—' }}</div>
            <div class="m-acc-metric-label">商品</div>
          </div>
          <div class="m-acc-metric-divider"></div>
          <div class="m-acc-metric">
            <div class="m-acc-metric-val m-acc-metric-val-accent">{{ acc.todaySales ?? '—' }}</div>
            <div class="m-acc-metric-label">今日销售</div>
          </div>
        </div>

        <!-- 底部：健康分 + Cookie状态 + 地区（紧凑一行） -->
        <div class="m-acc-footer">
          <div v-if="acc.health != null" class="m-acc-health">
            <span class="m-acc-health-label">健康</span>
            <div class="m-acc-health-bar">
              <div
                class="m-acc-health-progress"
                :class="healthBarClass(acc.health)"
                :style="{ width: healthPercent(acc.health) + '%' }"
              ></div>
            </div>
            <span class="m-acc-health-num" :class="healthBarClass(acc.health)">{{ acc.health }}</span>
          </div>
          <span class="m-acc-cookie" :class="cookieStatusClass(acc)">
            <MIcon name="shield" :size="11" />
            {{ cookieStatusText(acc) }}
          </span>
          <span v-if="accountArea(acc)" class="m-acc-area">
            <MIcon name="globe" :size="11" />
            {{ accountArea(acc) }}
          </span>
        </div>
      </div>
    </div>

    <button
      v-if="dataAvailable && accounts.length < listTotal"
      type="button"
      class="m-load-more"
      :disabled="loadingMore"
      @click="loadMore"
    >
      {{ loadingMore ? '加载中...' : `加载更多（${accounts.length}/${listTotal}）` }}
    </button>

    <div class="m-acc-tip">
      <MIcon name="warning" :size="16" />
      <span>账号详细管理与操作建议在PC端完成</span>
      <button class="m-tip-btn" @click="$emit('force-desktop')">进入桌面版</button>
    </div>

    <div class="m-safe-bottom"></div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import MIcon from './MIcon.vue'
import { getAccounts, getAccountSummary } from '../api/accounts.js'
import { accountCookieLabel, accountCookieStatus, accountWsConnected } from '../utils/accountAuth.js'
import { recordsOf } from '../utils/apiData.js'

defineEmits(['navigate', 'force-desktop', 'back'])

const accounts = ref([])
const loading = ref(true)
const loadingMore = ref(false)
const dataAvailable = ref(false)
const summaryAvailable = ref(false)
const error = ref('')
const page = ref(1)
const listTotal = ref(0)
const stats = reactive({ total: 0, online: 0, normal: 0, abnormal: 0 })

function appendError(message) {
  if (!message) return
  error.value = error.value ? `${error.value} ${message}` : message
}

async function loadAccounts() {
  loading.value = true
  error.value = ''
  dataAvailable.value = false
  summaryAvailable.value = false
  const [listResult, summaryResult] = await Promise.allSettled([
    getAccounts({ current: 1, size: 100 }),
    getAccountSummary()
  ])
  if (listResult.status === 'fulfilled') {
    const data = listResult.value?.data
    const list = recordsOf(data)
    accounts.value = list
    listTotal.value = Number(data?.total ?? list.length) || 0
    page.value = 1
    dataAvailable.value = true
  } else {
    accounts.value = []
    listTotal.value = 0
    dataAvailable.value = false
    appendError('账号列表暂不可用，当前不会把加载失败显示为零个账号。')
  }
  if (summaryResult.status === 'fulfilled' && summaryResult.value?.data) {
    const summary = summaryResult.value.data
    stats.total = Number(summary.total ?? 0) || 0
    stats.online = Number(summary.wsOnline ?? 0) || 0
    stats.normal = Number(summary.normal ?? 0) || 0
    stats.abnormal = Number(summary.cookieWarn ?? summary.verify ?? 0) || 0
    summaryAvailable.value = true
  } else {
    appendError('账号汇总暂不可用；全局指标以“—”显示。')
  }
  loading.value = false
}

async function loadMore() {
  if (loadingMore.value || !dataAvailable.value || accounts.value.length >= listTotal.value) return
  loadingMore.value = true
  try {
    const nextPage = page.value + 1
    const res = await getAccounts({ current: nextPage, size: 100 })
    const nextRecords = recordsOf(res?.data)
    const seen = new Set(accounts.value.map(account => String(account.id)))
    accounts.value.push(...nextRecords.filter(account => !seen.has(String(account.id))))
    listTotal.value = Number(res?.data?.total ?? listTotal.value) || listTotal.value
    page.value = nextPage
  } catch {
    appendError('更多账号加载失败，已保留当前列表。')
  } finally {
    loadingMore.value = false
  }
}

function accountName(acc) {
  if (!acc) return '未知账号'
  return acc.name || acc.nickname || acc.displayName || acc.accountNote || `账号${acc.id || ''}`
}

function accountLevel(acc) {
  if (!acc) return '-'
  const lv = acc.accountLevel || acc.sellerLevel || acc.fishShopLevel || acc.level
  return lv != null && lv !== '' ? lv : '-'
}

function accountArea(acc) {
  if (!acc) return ''
  const province = acc.province
  const city = acc.city
  if (province && city) return `${province} ${city}`
  if (province) return province
  if (city) return city
  if (acc.area) return acc.area
  if (acc.ipLocation) return acc.ipLocation
  return ''
}

function cookieStatusText(acc) {
  if (!acc) return '正常'
  return accountCookieLabel(acc)
}

function cookieStatusClass(acc) {
  if (!acc) return 'm-acc-tag-green'
  const cs = accountCookieStatus(acc)
  if (cs == null) return 'm-acc-tag-gray'
  if (cs === 0) return 'm-acc-tag-red'
  if (cs === 2) return 'm-acc-tag-orange'
  return 'm-acc-tag-green'
}

function wsStatusText(acc) {
  const connected = accountWsConnected(acc)
  if (connected === true) return '在线'
  if (connected === false) return '离线'
  return '未知'
}

function wsStatusClass(acc, target) {
  const connected = accountWsConnected(acc)
  if (target === 'dot') {
    return connected === true ? 'm-acc-status-dot-online' : (connected === false ? 'm-acc-status-dot-offline' : 'm-acc-status-dot-unknown')
  }
  return connected === true ? 'm-acc-status-pill-on' : (connected === false ? 'm-acc-status-pill-off' : 'm-acc-status-pill-unknown')
}

function healthPercent(score) {
  const num = Number(score)
  if (isNaN(num)) return 0
  if (num < 0) return 0
  if (num > 100) return 100
  return num
}

function healthBarClass(score) {
  const num = Number(score)
  if (isNaN(num)) return 'm-acc-health-progress-low'
  if (num >= 80) return 'm-acc-health-progress-high'
  if (num >= 60) return 'm-acc-health-progress-mid'
  return 'm-acc-health-progress-low'
}

function onAvatarError(e, acc) {
  if (acc) {
    acc.avatarUrl = ''
    acc.avatar = ''
  }
}

onMounted(() => {
  loadAccounts()
})
</script>

<style scoped>
.m-accounts {
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
.m-state-warning {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-bottom: 12px; padding: 12px 14px; border: 1px solid #f6d58a;
  border-radius: 14px; color: #8a4b08; background: #fff8e8;
  font-size: 12px; line-height: 1.5;
}
.m-state-warning button {
  min-height: 40px; padding: 0 14px; flex-shrink: 0; border: 1px solid #e2ad3b;
  border-radius: 12px; color: #744006; background: white; font-weight: 600;
}

.m-acc-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.m-acc-stat-card {
  background: white;
  border-radius: 16px;
  padding: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
  border: 1px solid #f0f4fa;
}
.m-acc-stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.m-acc-stat-icon-blue {
  background: linear-gradient(135deg, #e8f1ff, #d4e4ff);
  color: #0d6bff;
}
.m-acc-stat-icon-green {
  background: linear-gradient(135deg, #e2f8ee, #cdf2df);
  color: #16bf78;
}
.m-acc-stat-icon-gray {
  background: linear-gradient(135deg, #eef1f6, #e2e7f0);
  color: #8c98ae;
}
.m-acc-stat-icon-red {
  background: linear-gradient(135deg, #ffecec, #ffd8d8);
  color: #ff5252;
}
.m-acc-stat-info { flex: 1; min-width: 0; }
.m-acc-stat-val { font-size: 22px; font-weight: 800; color: #15213d; line-height: 1.1; }
.m-acc-stat-label { font-size: 12px; color: #8c98ae; margin-top: 3px; }

.m-loading { text-align: center; padding: 40px; color: #8c98ae; font-size: 14px; }

.m-empty {
  text-align: center;
  padding: 60px 20px;
}
.m-empty-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e8f1ff, #d4e4ff);
  color: #0d6bff;
  display: flex;
  align-items: center;
  justify-content: center;
}
.m-empty-text { font-size: 16px; font-weight: 600; color: #15213d; margin-bottom: 6px; }
.m-empty-desc { font-size: 13px; color: #8c98ae; }

.m-acc-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.m-acc-card {
  background: white;
  border-radius: 16px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
  border: 1px solid #f0f4fa;
}

.m-acc-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.m-acc-avatar-wrap {
  position: relative;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
}
.m-acc-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  overflow: hidden;
  background: #f4f7fc;
}
.m-acc-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.m-acc-avatar-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e8f1ff, #d4e4ff);
  color: #0d6bff;
}
.m-acc-status-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid white;
  box-sizing: border-box;
  box-shadow: 0 1px 3px rgba(31, 53, 94, 0.15);
}
.m-acc-status-dot-online { background: #16bf78; }
.m-acc-status-dot-offline { background: #c2cad6; }
.m-acc-status-dot-unknown { background: #ffb547; }
.m-acc-card-title {
  flex: 1;
  min-width: 0;
}
.m-acc-name {
  font-size: 16px;
  font-weight: 700;
  color: #15213d;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-acc-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  min-width: 0;
}
.m-acc-level {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 100px;
  background: linear-gradient(135deg, #fff4e0, #ffe7c2);
  color: #ff9f22;
  flex-shrink: 0;
}
.m-acc-level :deep(svg) { flex-shrink: 0; }
.m-acc-uid {
  font-size: 11px;
  color: #8c98ae;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.m-acc-status-pill {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 100px;
}
.m-acc-status-pill-on {
  background: rgba(22, 191, 120, 0.12);
  color: #16bf78;
}
.m-acc-status-pill-off {
  background: rgba(140, 152, 174, 0.15);
  color: #8c98ae;
}
.m-acc-status-pill-unknown {
  background: rgba(255, 181, 71, 0.16);
  color: #a05b00;
}

/* 核心指标区：大号数字 + 分隔线 */
.m-acc-metrics {
  display: flex;
  align-items: center;
  margin-top: 14px;
  padding: 14px 0;
  border-top: 1px solid #f0f4fa;
  border-bottom: 1px solid #f0f4fa;
}
.m-acc-metric {
  flex: 1;
  min-width: 0;
  text-align: center;
}
.m-acc-metric-val {
  font-size: 22px;
  font-weight: 800;
  color: #15213d;
  line-height: 1.1;
}
.m-acc-metric-val-accent { color: #ff5b2e; }
.m-acc-metric-label {
  font-size: 11px;
  color: #8c98ae;
  margin-top: 4px;
}
.m-acc-metric-divider {
  width: 1px;
  height: 28px;
  background: #f0f4fa;
  flex-shrink: 0;
}

/* 底部：健康分 + Cookie + 地区 */
.m-acc-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.m-acc-health {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 120px;
}
.m-acc-health-label { font-size: 11px; color: #8c98ae; flex-shrink: 0; }
.m-acc-health-bar {
  flex: 1;
  height: 6px;
  background: #f0f4fa;
  border-radius: 100px;
  overflow: hidden;
  min-width: 40px;
}
.m-acc-health-progress {
  height: 100%;
  border-radius: 100px;
  transition: width 0.3s ease;
}
.m-acc-health-progress-high { background: linear-gradient(90deg, #16bf78, #2dd58a); }
.m-acc-health-progress-mid { background: linear-gradient(90deg, #ff9f22, #ffb94a); }
.m-acc-health-progress-low { background: linear-gradient(90deg, #ff5252, #ff7a7a); }
.m-acc-health-num {
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.m-acc-health-num.m-acc-health-progress-high { color: #16bf78; }
.m-acc-health-num.m-acc-health-progress-mid { color: #ff9f22; }
.m-acc-health-num.m-acc-health-progress-low { color: #ff5252; }

.m-acc-cookie {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 100px;
  flex-shrink: 0;
}
.m-acc-cookie :deep(svg) { flex-shrink: 0; }
.m-acc-cookie.m-acc-tag-green {
  background: rgba(22, 191, 120, 0.12);
  color: #16bf78;
}
.m-acc-cookie.m-acc-tag-red {
  background: rgba(255, 82, 82, 0.12);
  color: #ff5252;
}
.m-acc-cookie.m-acc-tag-orange {
  background: rgba(255, 159, 34, 0.12);
  color: #ff9f22;
}
.m-acc-cookie.m-acc-tag-gray {
  background: rgba(140, 152, 174, 0.15);
  color: #667085;
}
.m-acc-area {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: #8c98ae;
  flex-shrink: 0;
}
.m-acc-area :deep(svg) { flex-shrink: 0; }

.m-load-more {
  width: 100%;
  min-height: 44px;
  margin-top: 12px;
  border: 1px solid #cfdcf2;
  border-radius: 12px;
  color: #0d6bff;
  background: #fff;
  font-weight: 600;
}
.m-load-more:disabled { opacity: 0.6; }

.m-acc-tip {
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
.m-acc-tip :deep(svg) { color: #ff9f22; flex-shrink: 0; }
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
