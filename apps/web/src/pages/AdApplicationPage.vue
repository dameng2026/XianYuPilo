<template>
  <div class="ad-application-page">
    <div
      v-if="commercialState.available === false"
      class="global-notice warn commercial-unavailable"
      role="status"
    >
      <span>{{ commercialState.message }}</span>
      <button
        type="button"
        class="ads-link-btn"
        :disabled="loading.plans || loading.methods"
        @click="reloadCommercialServices"
      >
        {{ loading.plans || loading.methods ? '检测中...' : '重新检测' }}
      </button>
    </div>
    <div v-if="notice.text" :class="['global-notice', notice.type]">{{ notice.text }}</div>
    <div v-if="applicationIntent.pending" class="global-notice warn" role="status">
      上次广告申请结果尚未确认。当前页面已锁定原申请内容；再次提交只会复用同一持久化幂等键，禁止创建新意图。
    </div>

    <section class="ads-hero">
      <div class="ads-hero-copy">
        <span class="ads-hero-badge">首页广告合作</span>
        <h2>广告申请与支付以真实商业服务为准</h2>
        <p>
          仅在商业桥已配置并返回真实套餐与支付渠道后，才可提交申请或创建支付订单。
          开源端不会生成占位套餐，也不会在商业服务不可用时把申请保存在本地。
        </p>
        <div class="ads-hero-points">
          <span>套餐与价格来自商业服务</span>
          <span>支付状态以商业服务回执为准</span>
          <span>审核与上架时效不由开源端承诺</span>
        </div>
      </div>
      <div class="ads-hero-side">
        <div class="ads-hero-stat">
          <strong>{{ plans.length }}</strong>
          <span>可投放档位</span>
        </div>
        <div class="ads-hero-stat">
          <strong>{{ applications.length }}</strong>
          <span>我的申请</span>
        </div>
      </div>
    </section>

    <div class="ads-layout">
      <div class="ads-main">
        <CardPanel title="广告档位" desc="仅展示商业服务实时返回的套餐、价格与状态。" class="ads-section">
          <div v-if="loading.plans" class="ads-state">正在加载广告档位...</div>
          <EmptyState
            v-else-if="!plans.length"
            variant="dev"
            icon="📦"
            :title="commercialState.available === false ? '广告商业服务未配置' : '暂未返回可用广告档位'"
            :description="commercialState.available === false ? '当前不展示占位套餐，提交与支付操作已禁用。' : '请由管理员检查商业服务中的套餐配置。'"
          />
          <div v-else class="plan-grid">
            <article
              v-for="plan in plans"
              :key="plan.code || plan.id"
              :class="['plan-card', { active: form.planCode === plan.code }]"
              @click="handleSelectPlan(plan)"
            >
              <div class="plan-head">
                <div>
                  <small>{{ plan.positionLabel }}</small>
                  <h3>{{ plan.title }}</h3>
                </div>
                <span v-if="plan.recommended" class="plan-tag">推荐</span>
              </div>
              <strong class="plan-price">{{ formatPlanPrice(plan) }}</strong>
              <p class="plan-desc">{{ plan.description || '请在商业版后台补充套餐说明。' }}</p>
              <ul class="plan-benefits">
                <li v-for="benefit in plan.benefits || []" :key="benefit">{{ benefit }}</li>
              </ul>
            </article>
          </div>
        </CardPanel>

        <CardPanel title="提交申请" desc="商业服务确认接收申请后，才会继续创建真实支付订单。" class="ads-section">
          <form class="ads-form" @submit.prevent="handleSubmit">
            <div class="ads-form-grid">
              <label class="ads-field">
                <span>广告位类型</span>
                <select
                  v-model="form.positionType"
                  class="ads-input"
                  :disabled="commercialState.available !== true"
                  @change="handlePositionChange"
                >
                  <option value="home_carousel">首页轮播广告</option>
                  <option value="sidebar_text">首页文字广告</option>
                </select>
              </label>

              <label class="ads-field">
                <span>广告套餐</span>
                <select v-model="form.planCode" class="ads-input" :disabled="commercialState.available !== true">
                  <option value="">请选择套餐</option>
                  <option
                    v-for="plan in filteredPlans"
                    :key="plan.code || plan.id"
                    :value="plan.code"
                  >
                    {{ plan.title }} / {{ formatPlanPrice(plan) }}
                  </option>
                </select>
              </label>

              <label v-if="isTextMode" class="ads-field ads-field-full">
                <span>广告标题</span>
                <input
                  v-model="form.title"
                  class="ads-input"
                  :disabled="commercialState.available !== true"
                  maxlength="80"
                  placeholder="例如：课程报名 / 社群招募 / 服务咨询"
                />
              </label>

              <label class="ads-field ads-field-full">
                <span>公司或主体名称</span>
                <input
                  v-model="form.companyName"
                  class="ads-input"
                  :disabled="commercialState.available !== true"
                  maxlength="200"
                  placeholder="例如：XX 科技 / 个人主体姓名"
                />
              </label>

              <label class="ads-field ads-field-full">
                <span>跳转链接</span>
                <input
                  v-model="form.landingUrl"
                  class="ads-input"
                  :disabled="commercialState.available !== true"
                  maxlength="300"
                  placeholder="https://example.com/landing-page"
                />
              </label>

              <label class="ads-field ads-field-full">
                <span>联系人</span>
                <input
                  v-model="form.contact"
                  class="ads-input"
                  :disabled="commercialState.available !== true"
                  maxlength="120"
                  placeholder="微信 / 手机号 / 邮箱 / QQ 均可"
                />
              </label>
            </div>

            <div v-if="isCarouselMode" class="upload-block">
              <div class="upload-head">
                <span>轮播图素材</span>
                <small>建议 1600 × 600，提交后商业版后台可继续调整。</small>
              </div>
              <div class="upload-grid">
                <button
                  type="button"
                  class="upload-card"
                  :disabled="loading.upload || commercialState.available !== true"
                  @click="pickImage"
                >
                  <img
                    v-if="form.creativeImageUrl"
                    :src="form.creativeImageUrl"
                    alt="轮播图预览"
                    class="upload-preview"
                  />
                  <template v-else>
                    <strong>{{ loading.upload ? '上传中...' : '上传轮播图' }}</strong>
                    <span>支持 JPG / PNG / WEBP</span>
                  </template>
                </button>
                <div class="upload-meta">
                  <p>素材仅用于提交给已配置的商业服务；是否审核或展示以商业后台状态为准。</p>
                  <button
                    v-if="form.creativeImageUrl"
                    type="button"
                    class="ads-link-btn danger"
                    @click="clearUploadedImage"
                  >
                    移除图片
                  </button>
                </div>
              </div>
              <input
                ref="fileInput"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                class="hidden-input"
                :disabled="commercialState.available !== true"
                @change="handleImageChange"
              />
            </div>

            <label class="ads-field ads-field-full">
              <span>补充说明</span>
              <textarea
                v-model="form.remark"
                class="ads-textarea"
                :disabled="commercialState.available !== true"
                rows="4"
                maxlength="600"
                placeholder="可补充投放目标、上线时间、优惠信息等，非必填。"
              ></textarea>
              <small>{{ form.remark.length }} / 600</small>
            </label>

            <div class="payment-method-box">
              <div class="payment-method-head">
                <span>支付方式</span>
                <small v-if="loading.methods">正在加载商业版支付配置...</small>
                <small v-else-if="paymentState.available === false">{{ paymentState.message }}</small>
                <small v-else-if="!paymentMethods.length">当前还没有可用支付方式</small>
              </div>
              <div v-if="paymentState.available === false" class="payment-safety-notice" role="status">
                支付写入已失败关闭；仍可查看广告套餐与历史申请，但不会创建真实支付订单。
              </div>
              <div v-if="paymentMethods.length" class="method-list">
                <button
                  v-for="method in paymentMethods"
                  :key="method.channelType"
                  type="button"
                  :class="['method-card', { active: selectedPaymentMethod === method.channelType }]"
                  :disabled="commercialState.available !== true || paymentAttemptBlocksNewIntent"
                  @click="selectedPaymentMethod = method.channelType"
                >
                  <strong>{{ paymentMethodLabel(method) }}</strong>
                  <span>{{ paymentMethodDesc(method) }}</span>
                </button>
              </div>
            </div>

            <div class="ads-actions">
              <button type="button" class="ads-btn ads-btn-ghost" :disabled="loading.submit || applicationIntent.pending" @click="resetForm">
                清空
              </button>
              <button
                type="submit"
                class="ads-btn ads-btn-primary"
                :disabled="loading.submit || commercialState.available !== true || paymentState.available !== true || !paymentMethods.length || paymentAttemptBlocksNewIntent"
              >
                {{ loading.submit ? '正在提交...' : (applicationIntent.pending ? '复用原申请意图重试' : '提交至商业服务') }}
              </button>
            </div>
          </form>
        </CardPanel>
      </div>

      <aside class="ads-side">
        <CardPanel title="扫码支付" class="ads-section">
          <section
            v-if="paymentAttempt.visible"
            :class="['payment-attempt-safety', `is-${paymentAttempt.status}`]"
            role="status"
            aria-live="polite"
          >
            <div class="payment-attempt-head">
              <strong>{{ paymentAttemptStatusText }}</strong>
              <span v-if="paymentAttempt.attemptId">Attempt #{{ paymentAttempt.attemptId }}</span>
              <span v-else>{{ paymentAttempt.operation === 'close' ? '关闭操作核对' : 'Attempt ID 暂不可用' }}</span>
            </div>
            <p>{{ paymentAttempt.message }}</p>
            <dl class="payment-attempt-meta">
              <div>
                <dt>retrySafe</dt>
                <dd>{{ paymentAttempt.retrySafe ? 'true' : 'false' }}</dd>
              </div>
              <div>
                <dt>replaySafe</dt>
                <dd>{{ paymentAttempt.replaySafe ? 'true' : 'false' }}</dd>
              </div>
              <div v-if="paymentAttempt.orderNo">
                <dt>订单号</dt>
                <dd class="mono">{{ paymentAttempt.orderNo }}</dd>
              </div>
            </dl>
            <ul>
              <li>请勿更换支付方式，也不要清除本网站存储数据。</li>
              <li v-if="paymentAttempt.replaySafe">恢复时只复用当前保存的同一支付意图键，不会生成新键。</li>
              <li v-else>当前浏览器没有可安全恢复的原始键，请回到原标签页或先在商业服务人工核对。</li>
            </ul>
            <div class="payment-attempt-actions">
              <button
                v-if="paymentAttempt.operation === 'create' && paymentAttempt.replaySafe"
                type="button"
                class="ads-btn ads-btn-primary"
                :disabled="currentPayment.opening"
                @click="recoverPaymentAttempt"
              >
                {{ currentPayment.opening ? '恢复中...' : '复用原支付意图检查 / 恢复' }}
              </button>
              <button
                v-if="paymentAttempt.orderNo"
                type="button"
                class="ads-btn ads-btn-ghost"
                :disabled="currentPayment.refreshing || currentPayment.closing || currentPayment.opening"
                @click="verifyPaymentAttemptOrder"
              >
                {{ currentPayment.refreshing ? '核对中...' : '查询商业订单核对' }}
              </button>
            </div>
          </section>
          <div v-if="currentPayment.opening" class="ads-state">正在创建支付订单...</div>
          <EmptyState
            v-else-if="!currentPayment.order"
            variant="default"
            icon="💳"
            title="暂无待支付订单"
            :description="commercialState.available === false ? '广告商业服务不可用，无法创建或查询真实支付订单。' : (paymentState.available === false ? '支付幂等能力未通过验证，当前只允许查看历史申请。' : '商业服务返回支付订单后，这里会显示二维码与状态。')"
          />
          <div v-else class="payment-panel">
            <div class="payment-top">
              <div>
                <strong>{{ currentPayment.application?.title || currentPayment.application?.planTitle || '广告支付' }}</strong>
                <span>{{ currentPayment.application?.applicationNo || currentPayment.order.orderNo }}</span>
              </div>
              <i :class="['payment-status', { paid: currentPayment.order.paid }]">
                {{ currentPayment.order.statusText }}
              </i>
            </div>

            <div class="payment-qr-wrap">
              <img
                v-if="currentPayment.order.qrImage"
                :src="currentPayment.order.qrImage"
                alt="支付二维码"
                class="payment-qr"
              />
              <div v-else class="payment-qr-fallback">二维码待生成</div>
            </div>

            <div class="payment-meta">
              <div class="payment-row">
                <span>支付金额</span>
                <strong>{{ currentPayment.order.amount || `￥${currentPayment.order.amountYuan || 0}` }}</strong>
              </div>
              <div class="payment-row">
                <span>支付方式</span>
                <strong>{{ paymentMethodLabel(currentPayment.order) }}</strong>
              </div>
              <div class="payment-row">
                <span>订单号</span>
                <strong class="mono">{{ currentPayment.order.orderNo }}</strong>
              </div>
            </div>

            <p class="payment-tip">
              扫码后可刷新查询商业服务的订单状态；审核与投放状态以商业后台回执为准。
            </p>
            <p v-if="currentPayment.pollError" class="payment-poll-error" role="status" aria-live="polite">
              {{ currentPayment.pollError }}
            </p>

            <div class="payment-actions">
              <button
                type="button"
                class="ads-btn ads-btn-ghost"
                :disabled="commercialState.available !== true || currentPayment.refreshing || currentPayment.closing || currentPayment.opening"
                @click="refreshCurrentOrder()"
              >
                {{ currentPayment.refreshing ? '刷新中...' : '刷新状态' }}
              </button>
              <button
                type="button"
                class="ads-btn ads-btn-danger"
                :disabled="commercialState.available !== true || paymentState.available !== true || currentPayment.closing || currentPayment.refreshing || currentPayment.opening || currentPayment.order.paid"
                @click="closeCurrentOrder"
              >
                {{ currentPayment.closing ? '关闭中...' : '关闭订单' }}
              </button>
            </div>
          </div>
        </CardPanel>

        <CardPanel title="我的申请记录" class="ads-section">
          <template #action>
            <button class="ads-link-btn" type="button" :disabled="loading.records" @click="loadApplications">
              {{ loading.records ? '刷新中...' : '刷新' }}
            </button>
          </template>

          <div v-if="loading.records" class="ads-state">正在加载申请记录...</div>
          <EmptyState
            v-else-if="!applications.length"
            variant="default"
            icon="📝"
            title="还没有广告申请"
            description="商业服务返回真实申请后，这里会显示其支付与审核状态；历史本地记录仅供只读查看。"
          />
          <div v-else class="application-list">
            <article v-for="item in applications" :key="item.id" class="application-card">
              <div class="application-head">
                <div>
                  <strong>{{ item.title || item.planTitle || item.positionLabel }}</strong>
                  <span>{{ item.applicationNo || `#${item.id}` }}</span>
                </div>
                <i :class="['application-status', statusClass(item.status)]">
                  {{ item.statusLabel || getAdApplicationStatusText(item.status) }}
                </i>
              </div>

              <div class="application-body">
                <img
                  v-if="item.creativeImageUrl"
                  :src="item.creativeImageUrl"
                  alt="广告素材"
                  class="application-thumb"
                />
                <div class="application-copy">
                  <div class="application-meta">
                    <span>{{ item.positionLabel }}</span>
                    <span>{{ item.paymentStatusLabel || getPaymentStatusText(item.paymentStatus) }}</span>
                    <span v-if="item.paymentAmountYuan">￥{{ item.paymentAmountYuan }}</span>
                  </div>
                  <p>
                    {{ item.statusMessage || (commercialState.available === false
                      ? '历史只读记录；无法确认是否已进入商业后台。'
                      : '商业服务暂未返回状态说明。') }}
                  </p>
                  <small>{{ item.contactValue || item.contact || '-' }}</small>
                </div>
              </div>

              <div class="application-actions">
                <button
                  v-if="commercialState.available === true && paymentState.available === true && item.paymentStatus !== 'paid' && paymentMethods.length"
                  type="button"
                  class="ads-link-btn"
                  :disabled="currentPayment.opening || paymentAttemptBlocksNewIntent"
                  @click="continuePayment(item)"
                >
                  继续支付
                </button>
                <button
                  v-if="commercialState.available === true && item.paymentOrderNo"
                  type="button"
                  class="ads-link-btn"
                  @click="inspectPayment(item)"
                >
                  查看订单
                </button>
              </div>
            </article>
          </div>
        </CardPanel>

        <CardPanel title="投放说明" class="ads-section">
          <ol class="ads-steps">
            <li>部署管理员需先配置商业桥，并由商业服务提供真实套餐与支付方式。</li>
            <li>商业服务未配置时，开源端不会提交、保存申请或创建支付订单。</li>
            <li>支付、审核、排期与上下架均以商业服务返回的状态为准。</li>
            <li>历史本地申请记录只读保留，不代表已进入任何审核或投放流程。</li>
          </ol>
        </CardPanel>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import CardPanel from '../components/CardPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import {
  closeAdPaymentOrder,
  createAdPaymentOrder,
  getAdPaymentMethods,
  getAdPaymentOrder,
  getAdPlans,
  listAdApplications,
  reduceAdPaymentOrder,
  submitAdApplication,
} from '../api/ads.js'
import { uploadImage } from '../api/misc.js'
import { withBrowserIntentLock } from '../utils/browserIntentLock.js'
import {
  buildAdApplicationPayload,
  createDefaultAdApplicationForm,
  filterAdPlansByPosition,
  formatPlanPrice,
  getAdApplicationStatusClass,
  getAdApplicationStatusText,
  getPaymentStatusText,
  isCarouselPosition,
  isTextPosition,
  normalizePaymentOrder,
  selectAdPlan,
  sortEnabledAdPlans,
  syncAdPlanSelection,
} from './ads/ad-application-model.js'

const notice = ref({ text: '', type: 'info' })
const commercialState = reactive({
  available: null,
  message: '正在确认广告商业服务状态，确认完成前提交与支付操作不可用。',
})
const paymentState = reactive({
  available: null,
  message: '正在验证支付订单幂等能力。',
})
const plans = ref([])
const applications = ref([])
const paymentMethods = ref([])
const fileInput = ref(null)
const selectedPaymentMethod = ref('wechat')
const loading = reactive({
  plans: false,
  records: false,
  methods: false,
  submit: false,
  upload: false,
})
const currentPayment = reactive({
  application: null,
  order: null,
  opening: false,
  refreshing: false,
  closing: false,
  paymentMethod: '',
  pollError: '',
  applicationId: null,
  orderNo: '',
})
const paymentAttempt = reactive({
  visible: false,
  status: '',
  operation: 'create',
  attemptId: null,
  retrySafe: false,
  replaySafe: false,
  message: '',
  orderNo: '',
  applicationId: null,
  paymentMethod: '',
})
const applicationIntent = reactive({
  pending: false,
  key: '',
  payload: null,
})
const form = reactive(createDefaultAdApplicationForm())

let paymentPollTimer = null
let paymentPollGeneration = 0
let paymentGeneration = 0
let paymentDisposed = false
let paymentRefreshInFlight = null
const APPLICATION_INTENT_STORAGE_KEY = 'xya:ad-application-intent'
const PAYMENT_INTENT_STORAGE_PREFIX = 'xya:ad-payment-intent:'
const PAYMENT_IDEMPOTENCY_PATTERN = /^[A-Za-z0-9_.:-]{16,128}$/

const filteredPlans = computed(() => filterAdPlansByPosition(plans.value, form.positionType))
const isCarouselMode = computed(() => isCarouselPosition(form.positionType))
const isTextMode = computed(() => isTextPosition(form.positionType))
const paymentAttemptBlocksNewIntent = computed(() => (
  paymentAttempt.visible
  && (
    paymentAttempt.status === 'unknown'
    || paymentAttempt.status === 'in_progress'
    || paymentAttempt.status === 'conflict'
    || (paymentAttempt.status === 'failed' && paymentAttempt.retrySafe)
  )
))
const paymentAttemptStatusText = computed(() => ({
  unknown: '支付结果未知，已锁定新意图',
  in_progress: '原支付意图仍在执行',
  failed: '商业桥明确未执行',
  conflict: '检测到不同支付意图',
}[paymentAttempt.status] || '支付操作需要核对'))

function unwrapData(payload) {
  return payload?.data ?? payload
}

function normalizeMethod(item) {
  return {
    channelType: String(item?.channelType || item?.paymentMethod || '').trim().toLowerCase(),
    providerType: String(item?.providerType || '').trim().toLowerCase(),
    configName: String(item?.configName || item?.channelName || '').trim(),
  }
}

function getUploadImageUrl(payload) {
  const data = unwrapData(payload)
  return data?.imageUrl || data?.url || data?.data?.url || data?.data?.imageUrl || payload?.imageUrl || payload?.url || ''
}

function decorateApplication(item) {
  return {
    ...item,
    paymentStatus: String(item?.paymentStatus || '').toLowerCase(),
  }
}

function showNotice(text, type = 'info') {
  notice.value = { text, type }
  window.clearTimeout(showNotice.timer)
  showNotice.timer = window.setTimeout(() => {
    notice.value = { text: '', type: 'info' }
  }, 4200)
}
showNotice.timer = null

function stopPaymentPolling() {
  paymentPollGeneration += 1
  if (paymentPollTimer) {
    window.clearTimeout(paymentPollTimer)
    paymentPollTimer = null
  }
}

function normalizeApplicationId(value) {
  const applicationId = Number(value || 0)
  return Number.isInteger(applicationId) && applicationId > 0 ? applicationId : null
}

function capturePaymentGuard(orderNo = currentPayment.orderNo) {
  return {
    generation: paymentGeneration,
    applicationId: normalizeApplicationId(currentPayment.applicationId || currentPayment.application?.id),
    orderNo: String(orderNo || '').trim(),
  }
}

function isPaymentGuardCurrent(guard) {
  return isPaymentOwnerCurrent(guard)
    && guard?.orderNo === String(currentPayment.orderNo || '').trim()
}

function isPaymentOwnerCurrent(guard) {
  return !paymentDisposed
    && guard?.generation === paymentGeneration
    && guard?.applicationId === normalizeApplicationId(currentPayment.applicationId || currentPayment.application?.id)
}

function beginPaymentScope(application, orderNo = '', { preserveOrder = false } = {}) {
  stopPaymentPolling()
  paymentGeneration += 1
  paymentRefreshInFlight = null
  const normalizedOrderNo = String(orderNo || '').trim()
  const currentOrderNo = String(currentPayment.order?.orderNo || '').trim()
  currentPayment.application = application || null
  currentPayment.applicationId = normalizeApplicationId(application?.id)
  currentPayment.orderNo = normalizedOrderNo
  currentPayment.paymentMethod = String(application?.paymentMethod || '')
  currentPayment.opening = false
  currentPayment.refreshing = false
  currentPayment.closing = false
  currentPayment.pollError = ''
  if (!preserveOrder || currentOrderNo !== normalizedOrderNo) currentPayment.order = null
  return capturePaymentGuard(normalizedOrderNo)
}

function isCommercialAvailabilityFailure(error) {
  const status = Number(error?.status || error?.code || 0)
  return status >= 500
    || error?.code === 'NETWORK_ERROR'
    || error?.code === 'TIMEOUT'
    || error?.timeout === true
    || error?.data?.status === 'unavailable'
}

function markCommercialUnavailable(error, fallback = '无法确认广告商业服务状态') {
  const rawMessage = typeof error === 'string' ? error : error?.message
  const message = String(rawMessage || fallback).trim().replace(/[。；;\s]+$/, '')
  commercialState.available = false
  commercialState.message = `${message}。当前不会提交或保存广告申请，所有支付操作已禁用；已有档位、支付方式和申请记录仅保留为上次成功快照。`
  paymentState.available = false
  paymentState.message = '商业服务不可用，支付已禁用。'
  stopPaymentPolling()
}

function markPaymentUnavailable(message) {
  paymentState.available = false
  paymentState.message = String(message || '无法确认支付幂等能力，支付已禁用。')
  stopPaymentPolling()
}

function paymentIntentStorageKey(applicationId, paymentMethod) {
  return `${PAYMENT_INTENT_STORAGE_PREFIX}${applicationId}:${paymentMethod}`
}

function paymentIntentKey(applicationId, paymentMethod) {
  if (!applicationId || !paymentMethod) return ''
  const storageKey = paymentIntentStorageKey(applicationId, paymentMethod)
  try {
    const existing = window.localStorage.getItem(storageKey) || ''
    if (PAYMENT_IDEMPOTENCY_PATTERN.test(existing)) return existing
    const randomPart = window.crypto?.randomUUID?.()
      || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
    const key = `ad-payment:${applicationId}:${randomPart}`
    if (!PAYMENT_IDEMPOTENCY_PATTERN.test(key)) throw new Error('支付意图键生成失败')
    window.localStorage.setItem(storageKey, key)
    if (window.localStorage.getItem(storageKey) !== key) throw new Error('支付意图键校验失败')
    return key
  } catch {
    markPaymentUnavailable('浏览器无法安全保存支付意图，支付已禁用；请恢复站点存储权限后重试。')
    return ''
  }
}

function clearPaymentIntent(applicationId, paymentMethod) {
  if (!applicationId || !paymentMethod) return
  try {
    window.localStorage.removeItem(paymentIntentStorageKey(applicationId, paymentMethod))
  } catch {
    // A confirmed close remains authoritative; a later create will still fail
    // closed if a new intent cannot be persisted and read back.
  }
}

function handleCommercialFailure(error, fallback, type = 'error') {
  if (isCommercialAvailabilityFailure(error)) {
    markCommercialUnavailable(error, fallback)
    return
  }
  showNotice(error?.message || fallback, type)
}

function clearPaymentAttempt() {
  Object.assign(paymentAttempt, {
    visible: false,
    status: '',
    operation: 'create',
    attemptId: null,
    retrySafe: false,
    replaySafe: false,
    message: '',
    orderNo: '',
    applicationId: null,
    paymentMethod: '',
  })
}

function rememberPaymentAttempt(error, status) {
  const operation = String(error?.data?.operation || 'create').toLowerCase()
  const orderNo = String(error?.data?.orderNo || '').trim()
  const isClose = operation === 'close'
  const defaultMessage = isClose
    ? '关闭订单结果未知，请先查询商业服务核对；重复关闭只会复用同一稳定幂等键。'
    : '支付订单创建结果需要核对；系统已锁定不同支付意图。'
  Object.assign(paymentAttempt, {
    visible: true,
    status,
    operation,
    attemptId: Number(error?.data?.attemptId || 0) || null,
    retrySafe: error?.data?.retrySafe === true,
    replaySafe: error?.data?.replaySafe === true,
    message: String(error?.message || defaultMessage),
    orderNo,
    applicationId: Number(currentPayment.application?.id || 0) || null,
    paymentMethod: String(currentPayment.paymentMethod || selectedPaymentMethod.value || ''),
  })
}

function handlePaymentAttemptFailure(error, operationHint = 'create') {
  let normalizedError = error
  let attemptStatus = String(error?.data?.status || error?.data?.attemptStatus || '').toLowerCase()
  const unavailable = attemptStatus === 'unavailable'
  if (!attemptStatus && !unavailable && isCommercialAvailabilityFailure(error)) {
    const isClose = operationHint === 'close'
    normalizedError = {
      ...error,
      message: isClose
        ? '关闭请求传输中断，结果未知；请先查询核对，重复关闭只会复用同一稳定幂等键。'
        : '支付订单请求传输中断，结果未知；请勿更换方式或清除数据，并复用原支付意图恢复。',
      data: {
        ...(error?.data || {}),
        status: 'unknown',
        operation: operationHint,
        orderNo: isClose ? String(currentPayment.order?.orderNo || '') : '',
        retrySafe: false,
        replaySafe: true,
      },
    }
    attemptStatus = 'unknown'
  }
  if (attemptStatus === 'unknown') {
    rememberPaymentAttempt(normalizedError, attemptStatus)
    const orderNo = String(normalizedError?.data?.orderNo || '').trim()
    currentPayment.orderNo = orderNo
    currentPayment.order = orderNo
      ? normalizePaymentOrder({ ...normalizedError.data, status: 'unknown', statusText: '创建结果待核对' })
      : null
    return true
  }
  if (attemptStatus === 'in_progress') {
    rememberPaymentAttempt(error, attemptStatus)
    return true
  }
  if (attemptStatus === 'failed' && error?.data?.retrySafe === true) {
    rememberPaymentAttempt(error, attemptStatus)
    return true
  }
  if (attemptStatus === 'conflict') {
    rememberPaymentAttempt(error, attemptStatus)
    showNotice(error?.message || '同一广告申请已有支付意图，请核对原订单后继续。', 'error')
    return true
  }
  if (attemptStatus === 'closed' || attemptStatus === 'expired') {
    clearPaymentIntent(currentPayment.application?.id, currentPayment.paymentMethod)
    clearPaymentAttempt()
    showNotice('原支付订单已明确关闭或过期，已释放旧意图；可再次创建新订单。', 'info')
    return true
  }
  return false
}

async function recoverPaymentAttempt() {
  if (currentPayment.opening || paymentAttempt.operation !== 'create') return
  if (!paymentAttempt.replaySafe) {
    showNotice('当前页面没有可安全重放的原始支付键，请回到原标签页或人工核对。', 'error')
    return
  }
  const application = currentPayment.application
    || applications.value.find(item => Number(item?.id) === paymentAttempt.applicationId)
  if (!application) {
    showNotice('无法恢复原广告申请上下文，请刷新申请列表后人工核对。', 'error')
    return
  }
  await openPaymentForApplication(application, paymentAttempt.paymentMethod)
}

async function verifyPaymentAttemptOrder() {
  if (!paymentAttempt.orderNo) return
  await refreshCurrentOrder(paymentAttempt.orderNo)
}

function startPaymentPolling(orderNo, paymentGuard = capturePaymentGuard(orderNo)) {
  stopPaymentPolling()
  if (commercialState.available !== true || !isPaymentGuardCurrent(paymentGuard)) return
  const generation = paymentPollGeneration
  const tick = async () => {
    paymentPollTimer = null
    if (generation !== paymentPollGeneration || !isPaymentGuardCurrent(paymentGuard)) return
    await refreshCurrentOrder(orderNo, { silent: true, guard: paymentGuard })
    if (
      generation === paymentPollGeneration
      && isPaymentGuardCurrent(paymentGuard)
      && commercialState.available === true
      && !['paid', 'closed', 'failed'].includes(currentPayment.order?.statusKey)
    ) {
      paymentPollTimer = window.setTimeout(tick, 4000)
    }
  }
  paymentPollTimer = window.setTimeout(tick, 4000)
}

function pickImage() {
  if (commercialState.available !== true) {
    markCommercialUnavailable('广告商业服务尚未确认可用')
    return
  }
  fileInput.value?.click()
}

function clearUploadedImage() {
  form.creativeImageUrl = ''
  if (fileInput.value) fileInput.value.value = ''
}

function statusClass(status) {
  return getAdApplicationStatusClass(status)
}

function paymentMethodLabel(method) {
  const channel = String(method?.channelType || method?.paymentMethod || '').toLowerCase()
  if (channel === 'alipay') return '支付宝'
  if (channel === 'wechat') return '微信支付'
  return String(method?.configName || method?.channelName || '').trim() || '未知支付渠道'
}

function paymentMethodDesc(method) {
  const provider = String(method?.providerType || '').toLowerCase()
  if (provider === 'yipay') return '易支付通道'
  if (provider === 'official') return '官方直连通道'
  return '由商业服务提供'
}

function resetForm() {
  if (applicationIntent.pending) {
    showNotice('原广告申请结果尚未确认，禁止清空或更换申请意图。', 'warn')
    return
  }
  Object.assign(form, createDefaultAdApplicationForm())
  form.planCode = syncAdPlanSelection(plans.value, form.positionType, '')
}

function applicationIntentPayload() {
  return buildAdApplicationPayload(form)
}

function loadApplicationIntent() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(APPLICATION_INTENT_STORAGE_KEY) || 'null')
    if (!parsed || !PAYMENT_IDEMPOTENCY_PATTERN.test(String(parsed.key || '')) || !parsed.payload) return
    if (parsed.status === 'confirmed') return
    applicationIntent.pending = true
    applicationIntent.key = String(parsed.key)
    applicationIntent.payload = parsed.payload
    Object.assign(form, createDefaultAdApplicationForm(), parsed.payload)
  } catch {
    // A malformed record cannot be trusted as an issued intent. The next
    // write still has to persist and read back a new key before it can run.
  }
}

function persistApplicationIntent(payload) {
  const normalized = JSON.stringify(payload)
  try {
    const existing = JSON.parse(window.localStorage.getItem(APPLICATION_INTENT_STORAGE_KEY) || 'null')
    if (existing?.key && PAYMENT_IDEMPOTENCY_PATTERN.test(String(existing.key))) {
      if (existing.status === 'confirmed') {
        if (JSON.stringify(existing.payload) === normalized) {
          showNotice('相同广告申请已获得商业服务确认，请刷新申请列表，禁止重复提交。', 'warn')
          return ''
        }
        window.localStorage.removeItem(APPLICATION_INTENT_STORAGE_KEY)
      } else {
        if (JSON.stringify(existing.payload) !== normalized) {
          showNotice('已有结果未确认的广告申请；禁止更换内容或生成新幂等键。', 'error')
          return ''
        }
        applicationIntent.pending = true
        applicationIntent.key = String(existing.key)
        applicationIntent.payload = existing.payload
        return applicationIntent.key
      }
    }
    const randomPart = window.crypto?.randomUUID?.()
      || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
    const key = `ad-application:${randomPart}`
    if (!PAYMENT_IDEMPOTENCY_PATTERN.test(key)) throw new Error('申请意图键生成失败')
    const record = { key, payload, status: 'pending' }
    window.localStorage.setItem(APPLICATION_INTENT_STORAGE_KEY, JSON.stringify(record))
    const confirmed = JSON.parse(window.localStorage.getItem(APPLICATION_INTENT_STORAGE_KEY) || 'null')
    if (confirmed?.key !== key || JSON.stringify(confirmed?.payload) !== normalized) {
      throw new Error('申请意图键校验失败')
    }
    applicationIntent.pending = true
    applicationIntent.key = key
    applicationIntent.payload = payload
    return key
  } catch {
    showNotice('浏览器无法安全保存广告申请意图，提交已禁用；请恢复站点存储权限后重试。', 'error')
    return ''
  }
}

function confirmApplicationIntent(application) {
  try {
    const record = JSON.parse(window.localStorage.getItem(APPLICATION_INTENT_STORAGE_KEY) || 'null')
    if (record?.key === applicationIntent.key) {
      // The provider confirmation makes replay data unnecessary. Overwrite
      // first so contact/creative details are removed even if deletion fails.
      window.localStorage.setItem(APPLICATION_INTENT_STORAGE_KEY, JSON.stringify({
        key: record.key,
        status: 'confirmed',
        confirmedAt: Date.now(),
        applicationId: Number(application?.id || 0) || null,
      }))
      window.localStorage.removeItem(APPLICATION_INTENT_STORAGE_KEY)
    }
  } catch {
    // If storage became unavailable, the original record remains fail-closed.
  }
  applicationIntent.pending = false
  applicationIntent.payload = null
}

function clearApplicationIntent() {
  try {
    window.localStorage.removeItem(APPLICATION_INTENT_STORAGE_KEY)
  } catch {
    // The confirmed remote response remains authoritative. A stale record can
    // only replay the same provider idempotency key, never create a new one.
  }
  applicationIntent.pending = false
  applicationIntent.key = ''
  applicationIntent.payload = null
}

function applicationWriteDefinitelyNotIssued(error) {
  const reason = String(error?.data?.reason || '')
  const status = Number(error?.status || error?.code || 0)
  return reason === 'commercial_bridge_not_configured'
    || reason === 'commercial_bridge_mutation_idempotency_required'
    || reason === 'commercial_bridge_payment_idempotency_required'
    || reason === 'commercial_bridge_paid_ad_capabilities_required'
    || status === 400
    || status === 422
}

function handlePositionChange() {
  form.planCode = syncAdPlanSelection(plans.value, form.positionType, form.planCode)
  if (isCarouselMode.value) {
    form.title = ''
  } else {
    form.creativeImageUrl = ''
  }
}

function handleSelectPlan(plan) {
  Object.assign(form, selectAdPlan(plan))
  form.planCode = syncAdPlanSelection(plans.value, form.positionType, form.planCode)
}

async function loadPlans() {
  loading.plans = true
  try {
    const rows = unwrapData(await getAdPlans())
    if (commercialState.available === false) return true
    plans.value = sortEnabledAdPlans(Array.isArray(rows) ? rows : [])
    form.planCode = syncAdPlanSelection(plans.value, form.positionType, form.planCode)
    return true
  } catch (error) {
    markCommercialUnavailable(error, '加载真实广告档位失败')
    return false
  } finally {
    loading.plans = false
  }
}

async function loadPaymentMethods() {
  loading.methods = true
  try {
    const rows = unwrapData(await getAdPaymentMethods())
    if (commercialState.available === false) return true
    paymentMethods.value = (Array.isArray(rows) ? rows : [])
      .map(normalizeMethod)
      .filter(item => item.channelType === 'wechat' || item.channelType === 'alipay')
    if (paymentMethods.value.length) {
      const available = paymentMethods.value.some(item => item.channelType === selectedPaymentMethod.value)
      selectedPaymentMethod.value = available ? selectedPaymentMethod.value : paymentMethods.value[0].channelType
    }
    paymentState.available = true
    paymentState.message = ''
    return true
  } catch (error) {
    if (error?.data?.reason === 'commercial_bridge_payment_idempotency_required') {
      markPaymentUnavailable(error?.message || '商业桥未证明支持支付订单幂等键，支付已禁用。')
      return true
    }
    markCommercialUnavailable(error, '加载真实支付方式失败')
    return false
  } finally {
    loading.methods = false
  }
}

async function loadApplications() {
  loading.records = true
  try {
    const data = unwrapData(await listAdApplications({ current: 1, size: 20 }))
    const records = Array.isArray(data?.records) ? data.records : []
    applications.value = records.map(decorateApplication)
    if (data?.commercialAvailable === false) {
      markCommercialUnavailable('广告商业服务未配置；以下内容仅为历史只读记录')
      return false
    }
    return true
  } catch (error) {
    handleCommercialFailure(error, '加载广告申请记录失败')
    return false
  } finally {
    loading.records = false
  }
}

async function reloadCommercialServices() {
  commercialState.available = null
  commercialState.message = '正在确认广告商业服务状态，确认完成前提交与支付操作不可用。'
  paymentState.available = null
  paymentState.message = '正在验证支付订单幂等能力。'
  const results = await Promise.all([loadPlans(), loadPaymentMethods(), loadApplications()])
  if (results.every(Boolean)) {
    commercialState.available = true
    commercialState.message = ''
    return
  }
  if (commercialState.available !== false) {
    markCommercialUnavailable('广告商业服务未能完成可用性确认')
  }
}

async function handleImageChange(event) {
  const file = event?.target?.files?.[0]
  if (!file) return
  if (commercialState.available !== true) {
    markCommercialUnavailable('广告商业服务尚未确认可用')
    if (fileInput.value) fileInput.value.value = ''
    return
  }
  loading.upload = true
  try {
    const result = await uploadImage(0, file)
    const imageUrl = getUploadImageUrl(result)
    if (!imageUrl) throw new Error('上传成功但未返回图片地址')
    form.creativeImageUrl = imageUrl
    showNotice('轮播图上传成功', 'success')
  } catch (error) {
    showNotice(error?.message || '上传轮播图失败', 'error')
  } finally {
    loading.upload = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function openPaymentForApplication(application, paymentMethod) {
  if (commercialState.available !== true) {
    markCommercialUnavailable('广告商业服务尚未确认可用')
    return
  }
  if (paymentState.available !== true) {
    markPaymentUnavailable(paymentState.message || '支付幂等能力尚未确认，支付已禁用。')
    return
  }
  if (currentPayment.opening) return
  const normalizedApplicationId = Number(application?.id || 0)
  const normalizedPaymentMethod = paymentMethod || selectedPaymentMethod.value
  if (!Number.isInteger(normalizedApplicationId) || normalizedApplicationId <= 0) {
    showNotice('商业服务未返回有效申请编号，未创建支付订单', 'error')
    return
  }
  if (paymentAttemptBlocksNewIntent.value) {
    const sameIntent = normalizedApplicationId === paymentAttempt.applicationId
      && normalizedPaymentMethod === paymentAttempt.paymentMethod
    if (!sameIntent || !paymentAttempt.replaySafe) {
      showNotice('当前支付意图仍待核对，已禁止更换申请或支付方式；请使用安全面板恢复或人工核对。', 'error')
      return
    }
  }
  const idempotencyKey = paymentIntentKey(normalizedApplicationId, normalizedPaymentMethod)
  if (!idempotencyKey) return
  const ownerGuard = beginPaymentScope(application)
  currentPayment.paymentMethod = normalizedPaymentMethod
  currentPayment.opening = true
  try {
    const response = await createAdPaymentOrder(normalizedApplicationId, {
      paymentMethod: normalizedPaymentMethod,
      idempotencyKey,
    })
    if (!isPaymentOwnerCurrent(ownerGuard)) return
    const incoming = normalizePaymentOrder(response)
    const orderNo = String(incoming.orderNo || '').trim()
    if (!orderNo) {
      currentPayment.pollError = '商业服务未返回可核对的订单号，已保留支付意图并停止轮询。'
      return
    }
    currentPayment.orderNo = orderNo
    const orderGuard = { ...ownerGuard, orderNo }
    const accepted = reduceAdPaymentOrder(null, incoming, orderGuard)
    if (!accepted) {
      currentPayment.pollError = '商业服务返回的支付订单与当前申请不一致，已保留支付意图并停止轮询。'
      return
    }
    clearPaymentAttempt()
    currentPayment.order = accepted
    if (accepted.paid) {
      showNotice('商业服务已确认订单支付状态；审核状态以商业后台回执为准', 'success')
      await loadApplications()
    } else {
      startPaymentPolling(orderNo, orderGuard)
      showNotice('支付订单已生成，请扫码完成支付', 'success')
    }
  } catch (error) {
    if (!isPaymentOwnerCurrent(ownerGuard)) return
    if (!handlePaymentAttemptFailure(error)) {
      currentPayment.order = null
      handleCommercialFailure(error, '创建支付订单失败')
    }
  } finally {
    if (isPaymentOwnerCurrent(ownerGuard)) currentPayment.opening = false
  }
}

async function refreshCurrentOrder(orderNo = currentPayment.order?.orderNo, options = {}) {
  if (commercialState.available !== true) {
    if (!options.silent) markCommercialUnavailable('广告商业服务尚未确认可用')
    return
  }
  if (currentPayment.closing) return
  const requestedOrderNo = String(orderNo || '').trim()
  const guard = options.guard || capturePaymentGuard(requestedOrderNo)
  if (!requestedOrderNo || guard.orderNo !== requestedOrderNo || !isPaymentGuardCurrent(guard)) return

  if (
    paymentRefreshInFlight
    && paymentRefreshInFlight.guard.generation === guard.generation
    && paymentRefreshInFlight.guard.applicationId === guard.applicationId
    && paymentRefreshInFlight.guard.orderNo === guard.orderNo
  ) {
    return paymentRefreshInFlight.promise
  }

  currentPayment.refreshing = !options.silent
  const operation = { guard, promise: null }
  operation.promise = (async () => {
    try {
      const incoming = normalizePaymentOrder(await getAdPaymentOrder(
        requestedOrderNo,
        options.silent ? { background: true, suppressGlobalError: true } : {},
      ))
      if (!isPaymentGuardCurrent(guard)) return false

      const previous = currentPayment.order
      const accepted = reduceAdPaymentOrder(previous, incoming, guard)
      if (!accepted) {
        currentPayment.pollError = '商业服务返回了不属于当前申请或订单的状态，已保留上次成功状态。'
        return false
      }
      currentPayment.order = accepted
      currentPayment.paymentMethod = String(accepted.paymentMethod || currentPayment.paymentMethod || '')
      currentPayment.pollError = ''
      const stateChanged = accepted !== previous

      if (stateChanged && accepted.statusKey === 'closed') {
        clearPaymentIntent(guard.applicationId, currentPayment.paymentMethod)
        clearPaymentAttempt()
        stopPaymentPolling()
      }
      if (stateChanged && accepted.paid) {
        stopPaymentPolling()
        showNotice('商业服务已确认支付；是否进入审核以申请状态回执为准', 'success')
        await loadApplications()
      }
      return stateChanged
    } catch (error) {
      if (!isPaymentGuardCurrent(guard)) return false
      if (options.silent) {
        currentPayment.pollError = '支付状态暂时无法刷新，已保留上次成功状态；系统会继续后台重试。'
      } else {
        handleCommercialFailure(error, '刷新支付状态失败')
      }
      return false
    }
  })()
  paymentRefreshInFlight = operation

  try {
    return await operation.promise
  } finally {
    if (paymentRefreshInFlight === operation) paymentRefreshInFlight = null
    if (isPaymentGuardCurrent(guard)) currentPayment.refreshing = false
  }
}

async function closeCurrentOrder() {
  if (commercialState.available !== true) {
    markCommercialUnavailable('广告商业服务尚未确认可用')
    return
  }
  if (currentPayment.closing) return
  const orderNo = String(currentPayment.order?.orderNo || currentPayment.orderNo || '').trim()
  const application = currentPayment.application
  if (!orderNo || !normalizeApplicationId(application?.id)) return
  const guard = beginPaymentScope(application, orderNo, { preserveOrder: true })
  currentPayment.closing = true
  try {
    const incoming = normalizePaymentOrder(await closeAdPaymentOrder(orderNo))
    if (!isPaymentGuardCurrent(guard)) return
    const accepted = reduceAdPaymentOrder(currentPayment.order, incoming, guard)
    if (!accepted) {
      currentPayment.pollError = '商业服务返回了不属于当前申请或订单的关闭结果，已保留上次成功状态。'
      return
    }
    currentPayment.order = accepted
    currentPayment.paymentMethod = String(accepted.paymentMethod || currentPayment.paymentMethod || '')
    if (accepted.statusKey !== 'closed') {
      currentPayment.pollError = '商业服务尚未确认订单已关闭，已保留当前状态；请稍后重新核对。'
      return
    }
    clearPaymentIntent(guard.applicationId, currentPayment.paymentMethod)
    clearPaymentAttempt()
    showNotice('订单已关闭', 'success')
    await loadApplications()
  } catch (error) {
    if (!isPaymentGuardCurrent(guard)) return
    if (!handlePaymentAttemptFailure(error, 'close')) {
      handleCommercialFailure(error, '关闭订单失败')
    }
  } finally {
    if (isPaymentGuardCurrent(guard)) currentPayment.closing = false
  }
}

async function continuePayment(item) {
  if (commercialState.available !== true) {
    markCommercialUnavailable('广告商业服务尚未确认可用')
    return
  }
  if (currentPayment.opening) return
  if (item.paymentOrderNo) {
    await inspectPayment(item)
    return
  }
  await openPaymentForApplication(item, item.paymentMethod || selectedPaymentMethod.value)
}

async function inspectPayment(item) {
  if (commercialState.available !== true) {
    markCommercialUnavailable('广告商业服务尚未确认可用')
    return
  }
  if (!item.paymentOrderNo) {
    await continuePayment(item)
    return
  }
  const guard = beginPaymentScope(item, item.paymentOrderNo)
  await refreshCurrentOrder(item.paymentOrderNo, { guard })
  if (isPaymentGuardCurrent(guard) && !['paid', 'closed', 'failed'].includes(currentPayment.order?.statusKey)) {
    startPaymentPolling(item.paymentOrderNo, guard)
  }
}

async function handleSubmit() {
  if (commercialState.available !== true) {
    markCommercialUnavailable('广告商业服务尚未确认可用')
    return
  }
  if (!form.planCode) return showNotice('请先选择广告套餐', 'warn')
  if (!form.companyName.trim()) return showNotice('请先填写公司或主体名称', 'warn')
  if (!form.landingUrl.trim()) return showNotice('请先填写跳转链接', 'warn')
  if (!form.contact.trim()) return showNotice('请先填写联系人', 'warn')
  if (isTextMode.value && !form.title.trim()) return showNotice('请先填写广告标题', 'warn')
  if (isCarouselMode.value && !form.creativeImageUrl.trim()) return showNotice('请先上传轮播图', 'warn')
  if (paymentState.available !== true || !paymentMethods.value.length) return showNotice('支付安全能力不可用，申请与支付写入已禁用', 'warn')
  if (paymentAttemptBlocksNewIntent.value) return showNotice('已有支付意图待核对，当前禁止提交新的广告支付意图', 'warn')
  if (loading.submit || currentPayment.opening) return

  const payload = applicationIntentPayload()
  let idempotencyKey = ''
  try {
    idempotencyKey = await withBrowserIntentLock(
      'ad-application-intent',
      () => persistApplicationIntent(payload),
    )
  } catch (error) {
    showNotice(error?.message || '无法取得跨标签页申请锁，提交已禁用。', 'error')
  }
  if (!idempotencyKey) return
  loading.submit = true
  try {
    const response = await submitAdApplication({ ...payload, idempotencyKey })
    const application = decorateApplication(unwrapData(response))
    confirmApplicationIntent(application)
    const recordsLoaded = await loadApplications()
    if (!recordsLoaded) {
      resetForm()
      showNotice('广告申请已由商业服务确认接收，但申请列表刷新失败；请勿再次提交申请。', 'warn')
      return
    }
    await openPaymentForApplication(application, selectedPaymentMethod.value)
    resetForm()
  } catch (error) {
    if (applicationWriteDefinitelyNotIssued(error)) {
      clearApplicationIntent()
      handleCommercialFailure(error, '广告申请写入能力不可用')
    } else {
      showNotice(error?.message || '广告申请结果未确认；只能复用原申请意图重试。', 'error')
    }
  } finally {
    loading.submit = false
  }
}

onMounted(async () => {
  loadApplicationIntent()
  await reloadCommercialServices()
})

onBeforeUnmount(() => {
  paymentDisposed = true
  paymentGeneration += 1
  paymentRefreshInFlight = null
  stopPaymentPolling()
  window.clearTimeout(showNotice.timer)
})
</script>

<style scoped>
.ad-application-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.commercial-unavailable {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.ads-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 18px;
  padding: 28px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(56, 136, 255, 0.18), transparent 34%),
    linear-gradient(135deg, #f8fbff 0%, #eef5ff 56%, #fdfefe 100%);
  border: 1px solid rgba(190, 211, 247, 0.95);
  box-shadow: 0 18px 48px rgba(38, 92, 176, 0.08);
}

.ads-hero-badge {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: #2d63ce;
  font-size: 12px;
  font-weight: 800;
}

.ads-hero h2 {
  margin: 14px 0 10px;
  color: #14213d;
  font-size: 28px;
  line-height: 1.15;
}

.ads-hero p {
  margin: 0;
  color: #60718c;
  line-height: 1.8;
}

.ads-hero-points {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.ads-hero-points span {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  color: #3e5371;
  font-size: 12px;
  font-weight: 700;
}

.ads-hero-side {
  display: grid;
  gap: 12px;
}

.ads-hero-stat {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 110px;
  padding: 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(214, 228, 249, 0.92);
}

.ads-hero-stat strong {
  color: #0f172a;
  font-size: 30px;
  line-height: 1;
}

.ads-hero-stat span {
  margin-top: 8px;
  color: #6b7c96;
  font-size: 13px;
}

.payment-safety-notice {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #f5c96b;
  border-radius: 10px;
  background: #fff8e8;
  color: #8a5a00;
  font-size: 12px;
  line-height: 1.6;
}

.payment-attempt-safety {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px;
  border: 1px solid #f0b44d;
  border-radius: 14px;
  background: #fff8e7;
  color: #714900;
}

.payment-attempt-safety.is-unknown,
.payment-attempt-safety.is-conflict {
  border-color: #f19a8e;
  background: #fff1ef;
  color: #8f2e22;
}

.payment-attempt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.payment-attempt-head strong {
  font-size: 14px;
}

.payment-attempt-head span {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.payment-attempt-safety p,
.payment-attempt-safety ul {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
}

.payment-attempt-safety ul {
  padding-left: 18px;
}

.payment-attempt-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.payment-attempt-meta div {
  min-width: 0;
  padding: 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.74);
}

.payment-attempt-meta dt {
  font-size: 11px;
  opacity: 0.78;
}

.payment-attempt-meta dd {
  overflow-wrap: anywhere;
  margin: 3px 0 0;
  font-size: 12px;
  font-weight: 800;
}

.payment-attempt-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.payment-attempt-actions .ads-btn {
  flex: 1 1 150px;
  min-width: 0;
}

.ads-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 20px;
  align-items: start;
}

.ads-main,
.ads-side {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.ads-section {
  border-radius: 20px;
  padding: 22px;
  box-shadow: 0 16px 40px rgba(32, 68, 132, 0.06);
}

.ads-state {
  color: #6e809b;
  font-size: 14px;
  line-height: 1.8;
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.plan-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 220px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid #dbe7f7;
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.plan-card:hover,
.plan-card.active {
  transform: translateY(-1px);
  border-color: #8fb6ff;
  box-shadow: 0 18px 34px rgba(37, 106, 214, 0.12);
}

.plan-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.plan-head small {
  display: block;
  color: #56749f;
  font-size: 12px;
  font-weight: 700;
}

.plan-head h3 {
  margin: 6px 0 0;
  color: #15243f;
  font-size: 18px;
}

.plan-tag {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: #eef5ff;
  color: #2968e8;
  font-size: 12px;
  font-weight: 800;
}

.plan-price {
  color: #0d6bff;
  font-size: 18px;
}

.plan-desc {
  margin: 0;
  color: #667892;
  line-height: 1.8;
}

.plan-benefits {
  margin: 0;
  padding-left: 18px;
  color: #42556f;
  line-height: 1.75;
}

.plan-benefits li + li {
  margin-top: 6px;
}

.ads-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.ads-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.ads-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ads-field-full {
  width: 100%;
}

.ads-field span {
  color: #32435d;
  font-size: 13px;
  font-weight: 700;
}

.ads-input,
.ads-textarea {
  width: 100%;
  color: #16233d;
  background: #fff;
  border: 1px solid #d8e3f4;
  border-radius: 14px;
  font-size: 14px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.ads-input {
  height: 44px;
  padding: 0 14px;
}

.ads-textarea {
  min-height: 120px;
  padding: 12px 14px;
  resize: vertical;
  line-height: 1.7;
}

.ads-input:focus,
.ads-textarea:focus {
  outline: none;
  border-color: #7ba7ff;
  box-shadow: 0 0 0 4px rgba(47, 107, 255, 0.1);
}

.ads-input:disabled,
.ads-textarea:disabled {
  color: #7b8799;
  background: #f3f6fa;
  cursor: not-allowed;
}

.ads-field small {
  color: #94a3b8;
  text-align: right;
  font-size: 12px;
}

.upload-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.upload-head span {
  color: #32435d;
  font-size: 13px;
  font-weight: 700;
}

.upload-head small {
  color: #7c8aa0;
  font-size: 12px;
}

.upload-grid {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 16px;
  align-items: center;
}

.upload-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  width: 220px;
  height: 132px;
  border: 1px dashed #9ab8ef;
  border-radius: 18px;
  background: linear-gradient(180deg, #fbfdff, #f3f8ff);
  color: #2f6bff;
}

.upload-card:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.upload-card strong {
  font-size: 15px;
}

.upload-card span {
  font-size: 12px;
}

.upload-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 18px;
}

.upload-meta p {
  margin: 0 0 8px;
  color: #60718c;
  line-height: 1.8;
}

.hidden-input {
  display: none;
}

.payment-method-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.payment-method-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.payment-method-head span {
  color: #32435d;
  font-size: 13px;
  font-weight: 700;
}

.payment-method-head small {
  color: #7c8aa0;
  font-size: 12px;
}

.method-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.method-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  border: 1px solid #dbe5f5;
  border-radius: 16px;
  background: #fff;
  text-align: left;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.method-card.active {
  border-color: #2f6bff;
  box-shadow: 0 14px 26px rgba(47, 107, 255, 0.12);
  transform: translateY(-1px);
}

.method-card:disabled {
  opacity: 0.62;
  cursor: not-allowed;
}

.method-card strong {
  color: #17315c;
  font-size: 14px;
}

.method-card span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.ads-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.ads-btn {
  min-width: 120px;
  height: 42px;
  border: 1px solid transparent;
  border-radius: 14px;
  font-size: 14px;
  font-weight: 800;
}

.ads-btn:disabled,
.ads-link-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ads-btn-ghost {
  color: #4b617f;
  background: #fff;
  border-color: #dbe5f5;
}

.ads-btn-primary {
  color: #fff;
  background: linear-gradient(90deg, #0d6cff, #1b86ff);
  box-shadow: 0 14px 30px rgba(13, 107, 255, 0.2);
}

.ads-btn-danger {
  color: #fff;
  background: linear-gradient(90deg, #ef4444, #f87171);
  box-shadow: 0 14px 30px rgba(239, 68, 68, 0.18);
}

.ads-link-btn {
  padding: 0;
  border: 0;
  background: transparent;
  color: #2f74f6;
  font-size: 12px;
  font-weight: 700;
}

.ads-link-btn.danger {
  color: #ef4444;
}

.payment-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.payment-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.payment-top strong {
  display: block;
  color: #17315c;
  font-size: 16px;
}

.payment-top span {
  display: block;
  margin-top: 4px;
  color: #7a8ba5;
  font-size: 12px;
}

.payment-status {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: #fff4e5;
  color: #d97706;
  font-size: 12px;
  font-style: normal;
  font-weight: 800;
}

.payment-status.paid {
  background: #e9f8f1;
  color: #179866;
}

.payment-qr-wrap {
  display: flex;
  justify-content: center;
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(180deg, #fbfdff, #f6f9ff);
  border: 1px solid #e2eaf7;
}

.payment-qr {
  width: 220px;
  height: 220px;
  object-fit: contain;
}

.payment-qr-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 220px;
  height: 220px;
  border-radius: 18px;
  background: #eef4ff;
  color: #6b7c96;
}

.payment-meta {
  display: grid;
  gap: 10px;
}

.payment-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #52647d;
  font-size: 13px;
}

.payment-row strong {
  color: #0f172a;
}

.mono {
  font-family: Consolas, 'Courier New', monospace;
  word-break: break-all;
}

.payment-tip {
  margin: 0;
  color: #60718c;
  font-size: 13px;
  line-height: 1.8;
}

.payment-poll-error {
  margin: 0;
  padding: 9px 11px;
  border: 1px solid #f6d58a;
  border-radius: 8px;
  color: #8a5a00;
  background: #fff9e8;
  font-size: 12px;
  line-height: 1.6;
}

.payment-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.application-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.application-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid #e4ecf8;
  background: linear-gradient(180deg, #ffffff, #fbfdff);
}

.application-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.application-head strong {
  display: block;
  color: #15243f;
  font-size: 15px;
}

.application-head span {
  display: block;
  margin-top: 4px;
  color: #93a2b7;
  font-size: 12px;
}

.application-status {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-style: normal;
  font-weight: 800;
}

.application-status.is-pending-payment {
  color: #0d6bff;
  background: #edf4ff;
}

.application-status.is-pending {
  color: #d97706;
  background: #fff4e5;
}

.application-status.is-approved,
.application-status.is-online {
  color: #179866;
  background: #e9f8f1;
}

.application-status.is-rejected,
.application-status.is-offline {
  color: #e11d48;
  background: #fff1f2;
}

.application-body {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 12px;
  margin-top: 12px;
}

.application-thumb {
  width: 84px;
  height: 64px;
  border-radius: 14px;
  object-fit: cover;
  border: 1px solid #e5edf9;
}

.application-copy {
  min-width: 0;
}

.application-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #6d7f9d;
  font-size: 12px;
}

.application-meta span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: #f3f7fd;
}

.application-copy p {
  margin: 10px 0 6px;
  color: #5f718b;
  font-size: 13px;
  line-height: 1.75;
}

.application-copy small {
  color: #8896a9;
  font-size: 12px;
}

.application-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
}

.ads-steps {
  margin: 0;
  padding-left: 18px;
  color: #556a86;
  line-height: 1.85;
}

.ads-steps li + li {
  margin-top: 8px;
}

@media (max-width: 1200px) {
  .ads-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .commercial-unavailable {
    align-items: flex-start;
    flex-direction: column;
  }

  .ads-hero,
  .plan-grid,
  .ads-form-grid,
  .method-list {
    grid-template-columns: minmax(0, 1fr);
  }

  .upload-grid,
  .application-body {
    grid-template-columns: minmax(0, 1fr);
  }

  .payment-actions {
    grid-template-columns: minmax(0, 1fr);
  }

  .ads-layout > *,
  .ads-hero > *,
  .plan-grid > *,
  .ads-form-grid > *,
  .method-list > *,
  .upload-grid > *,
  .application-body > *,
  .payment-actions > * {
    min-width: 0;
  }

  .ads-hero {
    padding: 14px;
  }

  .ads-hero h2 {
    font-size: 20px;
  }

  .ads-hero-stat {
    min-height: 80px;
    padding: 12px 14px;
  }

  .ads-hero-stat strong {
    font-size: 22px;
  }

  .ads-section {
    padding: 14px;
  }

  .plan-card {
    min-height: 0;
    padding: 14px;
  }

  .plan-head h3 {
    font-size: 16px;
  }

  .ads-input {
    height: 42px;
  }

  .upload-card {
    width: 100%;
  }

  .payment-qr,
  .payment-qr-fallback {
    width: 180px;
    height: 180px;
  }

  .payment-top {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .application-card {
    padding: 12px;
  }

  .application-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .application-meta {
    gap: 6px;
  }

  .application-thumb {
    width: 100%;
    height: 120px;
  }

  .ads-actions {
    flex-wrap: wrap;
  }

  .ads-btn {
    min-width: 0;
    flex: 1 1 auto;
  }
}
</style>
