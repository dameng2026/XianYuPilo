<template>
  <div class="auto-reply-shell">
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>
    <div v-if="availabilityNotice" class="global-notice warn auto-reply-availability-notice" role="status">
      <span>{{ availabilityNotice }} 重新同步成功前，所有自动回复范围写操作均已禁用。</span>
      <button type="button" class="retry-btn" :disabled="isRefreshing || scopeUpdating || batchUpdating" @click="refreshCurrentScope">
        {{ isRefreshing ? '同步中...' : '重新同步' }}
      </button>
    </div>

    <section class="auto-reply-hero">
      <div class="auto-reply-hero-head">
        <div class="auto-reply-hero-copy">
          <span class="auto-reply-hero-pill">Auto Reply Console</span>
          <h1>自动回复</h1>
          <p>
            把账号范围、商品范围和 AI 客服摘要收拢到一个主工作台里，让“哪里已配置”和“配置如何继承”在同一
            屏完成理解。
          </p>
        </div>

        <div class="auto-reply-hero-actions">
          <button type="button" class="auto-reply-action-button" :disabled="isRefreshing || scopeUpdating || batchUpdating" @click="refreshCurrentScope">
            <span class="auto-reply-button-dot"></span>
            {{ isRefreshing ? '同步中...' : '同步当前范围' }}
          </button>
          <button type="button" class="auto-reply-action-button primary" @click="goToAiCsSettings">
            <span class="auto-reply-button-dot"></span>
            前往 AI 客服配置
          </button>
        </div>
      </div>

      <div class="auto-reply-hero-main">
        <span class="auto-reply-hero-kicker">推荐方向</span>
        <h2>工作台总览</h2>
        <p>
          左侧选择账号与商品，右侧展示当前作用域、启用状态和 AI 配置摘要。信息层级更清楚，批量
          操作更像工作台而不是堆叠表单。
        </p>

        <div class="auto-reply-hero-pill-row">
          <span v-for="pill in heroPills" :key="pill">{{ pill }}</span>
        </div>

        <div class="auto-reply-hero-metrics">
          <article
            v-for="card in heroMetricCards"
            :key="card.label"
            class="auto-reply-hero-metric"
          >
            <b>{{ card.value }}</b>
            <span>{{ card.detail }}</span>
          </article>
        </div>
      </div>

      <aside class="auto-reply-hero-side">
        <div class="auto-reply-hero-side-top">
          <div>
            <h3>当前作用域</h3>
            <strong>{{ selectedAccountSummary.title }}</strong>
          </div>

          <label class="auto-reply-switch auto-reply-switch-large">
            <input
              type="checkbox"
              :checked="currentScopeEnabled"
              :disabled="!scopeWritesAvailable || scopeUpdating || batchUpdating"
              @change="toggleCurrentScope($event)"
            />
            <span class="auto-reply-slider"></span>
          </label>
        </div>

        <span class="auto-reply-side-pill">{{ scopeStatusLabel }}</span>

        <div class="auto-reply-side-note">
          <strong>本页只做范围管理</strong>
          <p>
            AI 客服的话术、知识库与聊天规则仍在「AI 客服配置」统一维护，避免策略和内容配置分散。
          </p>
        </div>

        <div class="auto-reply-side-list">
          <div class="auto-reply-side-item">
            <div>
              <b>作用层级</b>
              <strong>全局 → 账号 → 商品</strong>
            </div>
            <span class="auto-reply-status-chip blue">可继承</span>
          </div>

          <div class="auto-reply-side-item">
            <div>
              <b>批量选择</b>
              <strong>{{ selectedProductSummary.title }}</strong>
            </div>
            <span class="auto-reply-status-chip green">{{ selectedProductSummary.tag }}</span>
          </div>

          <div class="auto-reply-side-item">
            <div>
              <b>风险提醒</b>
              <strong>{{ riskSummaryText }}</strong>
            </div>
            <span class="auto-reply-status-chip amber">{{ riskSummaryTag }}</span>
          </div>
        </div>
      </aside>
    </section>

    <section class="auto-reply-workspace">
      <div class="auto-reply-left-column">
        <section class="auto-reply-panel auto-reply-account-panel">
          <div class="auto-reply-panel-head">
            <div>
              <h3>账号范围</h3>
              <p>先决定这次操作面向哪些账号，再继续细化到商品。</p>
            </div>
            <span class="auto-reply-tiny-chip">{{ accountsAvailable === true ? `${accounts.length} 个账号` : '账号数未知' }}</span>
          </div>

          <div v-if="accountsLoading" class="auto-reply-loading">账号加载中...</div>
          <div v-else-if="accountsAvailable !== true" class="auto-reply-unavailable">
            <strong>账号列表暂不可用</strong>
            <span>当前不会把加载失败显示为空账号，也不会基于不完整账号范围提交修改。</span>
            <button type="button" class="ghost" @click="loadAccounts">重新加载账号</button>
          </div>
          <div v-else class="auto-reply-panel-body auto-reply-account-list">
            <button
              v-for="card in accountCards"
              :key="card.key"
              type="button"
              class="auto-reply-account-item"
              :class="{ active: card.active }"
              :disabled="scopeUpdating || batchUpdating"
              @click="selectAccount(card.id)"
            >
              <div class="auto-reply-account-row">
                <div class="auto-reply-account-main">
                  <span class="auto-reply-account-badge" :class="{ 'is-all': card.isAll, 'has-avatar': !!card.avatarUrl }">
                    <svg v-if="card.isAll" class="auto-reply-account-icon" viewBox="0 0 24 24" aria-hidden="true">
                      <circle cx="9" cy="8" r="3.2" />
                      <path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke-linecap="round" stroke-linejoin="round" />
                      <circle cx="16.5" cy="9" r="2.6" />
                      <path d="M14 18.5c0-2.4 1.8-4 4-4s4 1.6 4 4" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <img v-else-if="card.avatarUrl" :src="card.avatarUrl" alt="" class="auto-reply-account-avatar" @error="onAvatarError(card)" />
                    <template v-else>{{ card.badge }}</template>
                  </span>
                  <div>
                    <strong>{{ card.name }}</strong>
                    <span>{{ card.description }}</span>
                  </div>
                </div>
                <span class="auto-reply-status-pill" :class="card.statusTone">{{ card.status }}</span>
              </div>

              <div v-if="card.showMetrics" class="auto-reply-account-stats">
                <div v-for="metric in card.metrics" :key="metric.label" class="auto-reply-mini-stat">
                  <b>{{ metric.value }}</b>
                  <span>{{ metric.label }}</span>
                </div>
              </div>
            </button>
          </div>
        </section>

        <section class="auto-reply-panel auto-reply-product-panel">
          <div class="auto-reply-panel-head">
            <div>
              <h3>商品范围</h3>
              <p>搜索、筛选并批量选择商品，决定哪些咨询会进入自动回复。</p>
            </div>
            <span class="auto-reply-tiny-chip">{{ productsAvailable === true ? `${products.length} 个商品` : '商品数未知' }}</span>
          </div>

          <div class="auto-reply-product-toolbar">
            <div class="auto-reply-search-row">
              <label class="auto-reply-search">
                <span class="auto-reply-search-icon"></span>
                <input v-model="productSearch" type="text" :disabled="productsAvailable !== true" placeholder="搜索商品标题、关键词或店铺标签" />
              </label>

              <button
                type="button"
                class="auto-reply-action-button primary"
                :disabled="batchUpdating || scopeUpdating || !scopeWritesAvailable || !products.length"
                @click="batchEnableAllProducts"
              >
                {{ batchUpdating ? '处理中...' : '一键全部开启' }}
              </button>
            </div>

            <div class="auto-reply-filter-row">
              <button
                v-for="option in productFilterOptions"
                :key="option.value"
                type="button"
                class="auto-reply-filter-chip"
                :class="{ active: productFilter === option.value }"
                :disabled="productsAvailable !== true"
                @click="productFilter = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div v-if="productsLoading" class="auto-reply-loading">商品加载中...</div>
          <div v-else-if="productsAvailable !== true" class="auto-reply-unavailable">
            <strong>商品范围暂不可用</strong>
            <span>请求失败不会显示为空商品；重新加载成功前不可提交范围修改。</span>
            <button type="button" class="ghost" @click="loadProducts">重新加载商品</button>
          </div>
          <div v-else-if="!filteredProducts.length" class="auto-reply-empty">当前筛选条件下暂无商品</div>
          <div v-else class="auto-reply-product-list">
            <button
              v-for="product in pagedFilteredProducts"
              :key="product.id"
              type="button"
              class="auto-reply-product-item"
              :class="{ selected: selectedProductIds.includes(product.id) }"
              :disabled="scopeUpdating || batchUpdating"
              @click="toggleProductSelect(product.id)"
            >
              <div class="auto-reply-product-top">
                <span class="auto-reply-checkbox" :class="{ checked: selectedProductIds.includes(product.id) }"></span>
                <div class="auto-reply-product-body">
                  <strong :title="product.title">{{ shortText(product.title, 36) }}</strong>
                  <div class="auto-reply-product-meta">
                    <span class="auto-reply-meta-badge" :class="productPrimaryStatus(product).tone">
                      {{ productPrimaryStatus(product).label }}
                    </span>
                    <span v-if="productSecondaryStatus(product)" class="auto-reply-meta-badge" :class="productSecondaryStatus(product).tone">
                      {{ productSecondaryStatus(product).label }}
                    </span>
                    <span class="auto-reply-meta-badge gray">
                      {{ accountLabelForProduct(product) }}
                    </span>
                  </div>
                </div>
              </div>
            </button>
          </div>

          <div v-if="filteredProducts.length > productVisibleLimit" class="auto-reply-load-more">
            <button type="button" class="ghost" @click="productVisibleLimit += 50">显示更多（剩余 {{ filteredProducts.length - productVisibleLimit }} 条）</button>
          </div>

          <div v-if="selectedProductIds.length" class="auto-reply-selection-bar">
            <div>
              <strong>{{ selectedProductSummary.title }}</strong>
              <span>{{ selectedProductSummary.description }}</span>
            </div>

            <div class="auto-reply-selection-actions">
              <button
                type="button"
                class="ghost"
                :disabled="batchUpdating || scopeUpdating || !scopeWritesAvailable"
                @click.stop="batchUpdateProducts(false)"
              >
                批量关闭
              </button>
              <button
                type="button"
                class="fill"
                :disabled="batchUpdating || scopeUpdating || !scopeWritesAvailable"
                @click.stop="batchUpdateProducts(true)"
              >
                批量开启
              </button>
            </div>
          </div>
        </section>
      </div>

      <div class="auto-reply-right-column">
        <section class="auto-reply-panel auto-reply-strategy-panel">
          <div class="auto-reply-panel-head">
            <div>
              <h3>自动回复策略</h3>
              <p>聚焦当前作用域的启用状态与继承关系；实际发送仍取决于模型、账号连接和平台状态。</p>
            </div>
            <span class="auto-reply-tiny-chip">当前配置</span>
          </div>

          <div class="auto-reply-panel-body auto-reply-strategy-body">
            <div class="auto-reply-strategy-top">
              <div class="auto-reply-strategy-copy">
                <h4>{{ strategyHeadline }}</h4>
                <p>{{ strategyDescription }}</p>

                <div class="auto-reply-insight-row">
                  <span class="auto-reply-insight-chip">{{ currentScopeBadge }}</span>
                  <span class="auto-reply-insight-chip">{{ selectedProductBadge }}</span>
                  <span class="auto-reply-insight-chip">{{ knowledgeBaseBadge }}</span>
                </div>
              </div>

              <div class="auto-reply-toggle-box">
                <b>总开关</b>
                <label class="auto-reply-switch">
                  <input
                    type="checkbox"
                    :checked="currentScopeEnabled"
                    :disabled="!scopeWritesAvailable || scopeUpdating || batchUpdating"
                    @change="toggleCurrentScope($event)"
                  />
                  <span class="auto-reply-slider"></span>
                </label>
                <strong>{{ scopeAvailable === true && productsAvailable === true ? (currentScopeEnabled ? '启用中' : '未启用') : '状态未知' }}</strong>
              </div>
            </div>

            <div class="auto-reply-metric-grid">
              <article
                v-for="card in scopeOverviewCards"
                :key="card.label"
                class="auto-reply-metric-card"
              >
                <b :class="card.tone">{{ card.label }}</b>
                <strong>{{ card.value }}</strong>
                <span>{{ card.detail }}</span>
              </article>
            </div>
          </div>
        </section>

        <div class="auto-reply-detail-grid">
          <section class="auto-reply-panel auto-reply-summary-panel">
            <div class="auto-reply-panel-head">
              <div>
                <h3>AI 客服配置摘要</h3>
                <p>保持只读摘要，不在这里直接改 Prompt，保证内容配置入口单一。</p>
              </div>
              <span class="auto-reply-tiny-chip">只读预览</span>
            </div>

            <div v-if="aiSummaryAvailable === true" class="auto-reply-panel-body auto-reply-summary-body">
              <div class="auto-reply-summary-block">
                <label>系统提示词</label>
                <p>{{ shortText(aiCsSummary.systemPrompt || '未配置系统提示词', 180) }}</p>
              </div>

              <div class="auto-reply-summary-block">
                <label>知识库</label>
                <p>{{ aiKnowledgeBaseSummary }}</p>
              </div>

              <div class="auto-reply-summary-block">
                <label>聊天规则</label>
                <p>{{ aiChatRuleSummary }}</p>
              </div>
            </div>
            <div v-else-if="aiSummaryLoading" class="auto-reply-loading">AI 客服摘要加载中...</div>
            <div v-else class="auto-reply-unavailable">
              <strong>AI 客服摘要暂不可用</strong>
              <span>当前无法确认主开关、知识库和聊天规则配置，范围写操作已锁定。</span>
              <button type="button" class="ghost" @click="loadAiCsSummary">重新加载摘要</button>
            </div>

            <div class="auto-reply-summary-footer">
              <button type="button" class="auto-reply-action-button primary full" @click="goToAiCsSettings">
                <span class="auto-reply-button-dot"></span>
                前往 AI 客服配置修改
              </button>
            </div>
          </section>

          <div class="auto-reply-side-stack">
            <section class="auto-reply-panel auto-reply-logic-panel">
              <div class="auto-reply-panel-head">
                <div>
                  <h3>配置继承逻辑</h3>
                  <p>这里说明开关优先级，不代表每条消息都已成功生成或送达。</p>
                </div>
              </div>

              <div class="auto-reply-panel-body auto-reply-logic-body">
                <div
                  v-for="step in logicSteps"
                  :key="step.step"
                  class="auto-reply-logic-step"
                  :data-step="step.step"
                >
                  <strong>{{ step.title }}</strong>
                  <span>{{ step.detail }}</span>
                </div>
              </div>
            </section>

            <section class="auto-reply-panel auto-reply-impact-panel">
              <div class="auto-reply-panel-head">
                <div>
                  <h3>当前影响面</h3>
                  <p>用运营语言说明这次切换具体会波及什么。</p>
                </div>
              </div>

              <div class="auto-reply-panel-body auto-reply-impact-body">
                <div
                  v-for="row in impactRows"
                  :key="row.label"
                  class="auto-reply-impact-row"
                >
                  <div>
                    <strong>{{ row.label }}</strong>
                    <span>{{ row.detail }}</span>
                  </div>
                  <div class="auto-reply-impact-value">{{ row.value }}</div>
                </div>

                <div class="auto-reply-impact-note">
                  <strong>设计重点</strong>
                  把“批量动作”从下角孤立按钮升级成和选择结果绑定的吸附条，同时让右侧策略卡更像结果页而不是表
                  单页，整体会更容易一眼看懂。
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getAccounts } from '../api/accounts.js'
import { getAutoReplyScopeProducts, getAutoReplyScopeStatus, updateProductAutoReplyScope, updateAccountAutoReplyScope, batchUpdateAutoReplyScope } from '../api/autoReplyScope.js'
import { getBusinessSettings } from '../api/businessSettings.js'
import { recordsOf, totalOf } from '../utils/apiData.js'
import { accountName, shortText } from '../utils/format.js'
import { confirmAction } from '../utils/confirmAction.js'
import { useDebouncedRef } from '../composables/useDebouncedRef.js'
import { friendlyError } from '../utils/friendlyError.js'

const emit = defineEmits(['navigate'])

const accounts = ref([])
const accountsLoading = ref(true)
const accountsAvailable = ref(null)
const brokenAvatarIds = ref(new Set())
const selectedAccountId = ref('')
const selectedProductIds = ref([])
const products = ref([])
const allProductsCache = ref([])
const productsLoading = ref(false)
const productsAvailable = ref(null)
const allProductsAvailable = ref(null)
const productSearch = ref('')
const debouncedProductSearch = useDebouncedRef(productSearch, 300)
const productFilter = ref('all')
const accountScopeStatus = ref({})
const globalEnabled = ref(false)
const scopeLoading = ref(true)
const scopeAvailable = ref(null)
const aiCsSummary = ref(null)
const aiSummaryLoading = ref(true)
const aiSummaryAvailable = ref(null)
const batchUpdating = ref(false)
const scopeUpdating = ref(false)
const isRefreshing = ref(false)
const error = ref('')
const success = ref('')
let productLoadVersion = 0

const scopeWritesAvailable = computed(() =>
  accountsAvailable.value === true &&
  scopeAvailable.value === true &&
  aiSummaryAvailable.value === true &&
  productsAvailable.value === true &&
  allProductsAvailable.value === true
)

const availabilityNotice = computed(() => {
  const unavailable = []
  if (accountsAvailable.value === false) unavailable.push('账号列表')
  if (scopeAvailable.value === false) unavailable.push('作用域状态')
  if (aiSummaryAvailable.value === false) unavailable.push('AI 客服摘要')
  if (productsAvailable.value === false) unavailable.push('当前商品范围')
  if (allProductsAvailable.value === false) unavailable.push('全部商品基线')
  return unavailable.length ? `${unavailable.join('、')}暂不可用。` : ''
})

const scopeStatusLabel = computed(() => {
  if (scopeLoading.value) return '自动回复状态同步中'
  if (!scopeWritesAvailable.value) return '自动回复状态未知'
  return currentScopeEnabled.value ? '自动回复已启用' : '自动回复未启用'
})

const productFilterOptions = [
  { value: 'all', label: '全部' },
  { value: 'enabled', label: '已开启' },
  { value: 'disabled', label: '未开启' },
  { value: 'inherited', label: '继承账号级' }
]

const knowledgeBaseCount = computed(() => {
  if (aiSummaryAvailable.value !== true) return null
  const data = aiCsSummary.value || {}
  const list = Array.isArray(data.knowledgeBases) ? data.knowledgeBases : []
  if (list.length) return list.length
  return data.knowledgeBase ? 1 : 0
})

const chatRuleCount = computed(() => {
  if (aiSummaryAvailable.value !== true) return null
  const data = aiCsSummary.value || {}
  const list = Array.isArray(data.chatRules) ? data.chatRules : []
  return list.length
})

const visibleProducts = computed(() => {
  const query = debouncedProductSearch.value.trim().toLowerCase()
  return products.value.filter((product) => {
    const matchesSearch = !query || (product.title || '').toLowerCase().includes(query)
    if (!matchesSearch) return false

    if (productFilter.value === 'enabled') return resolveProductEffective(product)
    if (productFilter.value === 'disabled') return !resolveProductEffective(product)
    if (productFilter.value === 'inherited') return product.auto_reply_enabled == null && product.account_enabled === true
    return true
  })
})

const filteredProducts = computed(() => visibleProducts.value)
// 商品列表分页显示：默认只渲染前 50 条，避免多账号场景下一次性渲染过多 DOM 导致卡顿
const productVisibleLimit = ref(50)
const pagedFilteredProducts = computed(() => filteredProducts.value.slice(0, productVisibleLimit.value))

const enabledProductCount = computed(() => products.value.filter(resolveProductEffective).length)
const inheritedProductCount = computed(() => products.value.filter((product) => product.auto_reply_enabled == null && product.account_enabled === true).length)
const selectedProducts = computed(() => products.value.filter((product) => selectedProductIds.value.includes(product.id)))
const selectedEnabledCount = computed(() => selectedProducts.value.filter(resolveProductEffective).length)
const selectedDisabledCount = computed(() => Math.max(selectedProducts.value.length - selectedEnabledCount.value, 0))
const selectedAccount = computed(() => accounts.value.find((account) => account.id === selectedAccountId.value) || null)

const aiKnowledgeBaseSummary = computed(() => {
  if (aiSummaryAvailable.value !== true) return '知识库配置状态未知，请重新加载 AI 客服摘要后核对。'
  if (knowledgeBaseCount.value > 1) return `已配置 ${knowledgeBaseCount.value} 份知识库：商品售卖说明、售后 FAQ 等摘要会在这里展示。`
  if (knowledgeBaseCount.value === 1) return '已配置 1 份知识库，后续可以继续扩展更多行业知识。'
  return '暂未配置知识库，建议先补充商品说明和售后 FAQ，避免回复内容过于空泛。'
})

const aiChatRuleSummary = computed(() => {
  if (aiSummaryAvailable.value !== true) return '聊天规则状态未知，请重新加载 AI 客服摘要后核对。'
  if (chatRuleCount.value > 0) return `已配置 ${chatRuleCount.value} 条聊天规则，具体内容与边界以 AI 客服配置页为准。`
  return '暂未配置聊天规则，将使用默认客服对话策略。'
})

const selectedAccountSummary = computed(() => {
  if (accountsAvailable.value !== true) {
    return {
      title: '账号范围\n状态未知',
      description: '当前无法确认完整账号列表，范围写操作已锁定。',
      badge: '待恢复'
    }
  }

  if (productsAvailable.value !== true) {
    return {
      title: '商品范围\n状态未知',
      description: '当前无法确认所选账号下的商品范围，范围写操作已锁定。',
      badge: '待恢复'
    }
  }

  if (selectedProductIds.value.length === 1) {
    const product = selectedProducts.value[0]
    return {
      title: `${shortText(product?.title || '商品', 16)}\n单品配置`,
      description: '当前只针对单个商品查看自动回复状态。',
      badge: '商品级'
    }
  }

  if (selectedProductIds.value.length > 1) {
    return {
      title: `${selectedProductIds.value.length} 个商品\n批量配置`,
      description: '当前准备批量修改多个商品的自动回复状态。',
      badge: '批量操作'
    }
  }

  if (selectedAccount.value) {
    return {
      title: `${accountName(selectedAccount.value)}\n账号配置`,
      description: '当前正在查看单个账号下的商品覆盖情况。',
      badge: '账号级'
    }
  }

  return {
    title: '全部账号\n全局配置',
    description: '当前正在汇总查看全部账号的自动回复覆盖情况。',
    badge: '全局'
  }
})

const selectedProductSummary = computed(() => {
  if (productsAvailable.value !== true) {
    return {
      title: '商品范围状态未知',
      description: '重新加载成功前不会把请求失败当作空商品，也不会提交批量修改。',
      tag: '待恢复'
    }
  }

  if (!selectedProductIds.value.length) {
    return {
      title: '暂无商品选中',
      description: '先在左侧商品列表里选择一个或多个商品，右侧会同步显示影响范围。',
      tag: '待选择'
    }
  }

  if (selectedProductIds.value.length === 1) {
    const product = selectedProducts.value[0]
    return {
      title: `已选中 1 个商品`,
      description: `当前聚焦商品「${shortText(product?.title || '', 24)}」的自动回复状态。`,
      tag: resolveProductEffective(product) ? '配置启用' : '待调整'
    }
  }

  return {
    title: `已选中 ${selectedProductIds.value.length} 个商品`,
    description: `批量操作将影响 ${selectedEnabledCount.value} 个已开启商品和 ${selectedDisabledCount.value} 个待调整商品。`,
    tag: '待操作'
  }
})

const scopeOverviewCards = computed(() => [
  {
    label: '配置启用范围',
    value: productsAvailable.value === true ? `${enabledProductCount.value} 个` : '—',
    detail: '已覆盖的商品数量，帮助用户立刻判断这次操作影响面。',
    tone: 'blue'
  },
  {
    label: '继承账号级',
    value: productsAvailable.value === true ? `${inheritedProductCount.value} 个` : '—',
    detail: '仍处于“跟随账号配置”的商品，适合提醒继续精细化管理。',
    tone: 'green'
  },
  {
    label: '待完善',
    value: pendingConfigCount.value == null ? '—' : `${pendingConfigCount.value} 项`,
    detail: '根据知识库与聊天规则情况给出轻量风险提醒。',
    tone: 'amber'
  }
])

const heroMetricCards = computed(() => [
  {
    label: '已开启自动回复',
    value: productsAvailable.value === true ? enabledProductCount.value : '—',
    detail: '已开启自动回复的商品，适合突出当前运营覆盖面。'
  },
  {
    label: '账号策略已同步',
    value: accountEnabledCount.value == null ? '—' : `${accountEnabledCount.value}/${accounts.value.length}`,
    detail: '账号级策略同步情况，避免用户误以为只改了商品层。'
  },
  {
    label: '当前商品启用覆盖率',
    value: coverageRate.value == null ? '—' : `${coverageRate.value}%`,
    detail: '按已加载商品中配置启用自动回复的占比计算，不代表消息送达率。'
  }
])

const heroPills = computed(() => [
  scopeAvailable.value === true ? (globalEnabled.value ? '全局主开关已开启' : '全局主开关未开启') : '全局主开关状态未知',
  accountsAvailable.value === true ? `${accounts.value.length} 个账号已接入` : '账号列表状态未知',
  productsAvailable.value === true ? `${products.value.length} 个商品已加载` : '商品范围状态未知',
  `当前命中范围：${selectedAccountSummary.value.badge}`
])

const strategyHeadline = computed(() => {
  if (!scopeWritesAvailable.value) return '自动回复范围 · 配置状态待恢复'
  if (selectedProductIds.value.length > 1) return `${selectedProductIds.value.length} 个商品 · 批量调整自动回复`
  if (selectedProductIds.value.length === 1) return `${shortText(selectedProducts.value[0]?.title || '当前商品', 18)} · 自动回复详情`
  if (selectedAccount.value) return `${accountName(selectedAccount.value)} · 账号回复配置`
  return '全部账号 · 智能回复配置'
})

const strategyDescription = computed(() => {
  if (!scopeWritesAvailable.value) {
    return '账号、作用域、商品或 AI 客服摘要存在未确认状态。重新同步成功前仅允许查看和恢复，不会提交范围修改。'
  }
  if (selectedProductIds.value.length > 1) {
    return '当前已选中的商品会一起应用开关状态。商品级关闭会覆盖账号级开启，开启后会立刻进入自动回复处理链路。'
  }
  if (selectedProductIds.value.length === 1) {
    return '单个商品可以单独覆盖账号级默认状态，适合对重点商品、特殊服务商品做更精细的控制。'
  }
  if (selectedAccount.value) {
    return '打开后，在模型已配置、账号连接可用等条件满足时，该账号下未单独关闭的商品会进入 AI 客服处理链路。商品级覆盖依然优先于账号级。'
  }
  return '打开后，在模型与账号连接可用时，当前选中范围内的咨询会进入 AI 客服处理链路。商品级关闭会覆盖账号级开启，账号级开启会覆盖全局默认状态。'
})

const currentScopeBadge = computed(() => {
  if (!scopeWritesAvailable.value) return '当前作用域：状态未知'
  if (selectedProductIds.value.length === 1) return '当前作用域：单个商品'
  if (selectedProductIds.value.length > 1) return `当前作用域：${selectedProductIds.value.length} 个商品`
  if (selectedAccount.value) return `当前作用域：${accountName(selectedAccount.value)}`
  return '当前作用域：全部账号（全局）'
})

const selectedProductBadge = computed(() => {
  if (productsAvailable.value !== true) return '批量选中：商品状态未知'
  if (!selectedProductIds.value.length) return '批量选中：未选择商品'
  return `批量选中：${selectedProductIds.value.length} 个商品`
})

const knowledgeBaseBadge = computed(() => aiSummaryAvailable.value === true
  ? `知识库：${knowledgeBaseCount.value} 份已绑定`
  : '知识库：状态未知')

const pendingConfigCount = computed(() => {
  if (accountsAvailable.value !== true || aiSummaryAvailable.value !== true) return null
  if (!accounts.value.length) return 0
  if (!knowledgeBaseCount.value && !chatRuleCount.value) return 1
  if (!knowledgeBaseCount.value || !chatRuleCount.value) return 1
  return 0
})

const riskSummaryText = computed(() => {
  if (pendingConfigCount.value == null) return '相关配置状态未知'
  if (pendingConfigCount.value > 0) return `${pendingConfigCount.value} 项配置待完善`
  return '知识库与规则配置已齐全'
})

const riskSummaryTag = computed(() => {
  if (pendingConfigCount.value == null) return '待恢复'
  return pendingConfigCount.value > 0 ? '建议补齐' : '已完善'
})

const coverageRate = computed(() => {
  if (productsAvailable.value !== true) return null
  if (!products.value.length) return 0
  return Math.round((enabledProductCount.value / products.value.length) * 100)
})

const accountEnabledCount = computed(() => {
  if (accountsAvailable.value !== true || scopeAvailable.value !== true) return null
  if (globalEnabled.value) return accounts.value.length
  return accounts.value.filter((account) => accountScopeStatus.value[account.id] === true).length
})

const logicSteps = [
  {
    step: '1',
    title: '全局主开关',
    detail: '决定系统是否具备自动回复能力。这里只展示状态，真正开启入口仍在 AI 客服配置页。'
  },
  {
    step: '2',
    title: '账号级范围',
    detail: '用于批量决定某个店铺下的默认回复状态，适合先做中层策略。'
  },
  {
    step: '3',
    title: '商品级覆盖',
    detail: '当单个商品需要单独开关时，以商品状态覆盖账号级和全局状态。'
  }
]

const impactRows = computed(() => [
  {
    label: '本次批量选择',
    detail: '将同步修改当前选中商品的商品级状态。',
    value: productsAvailable.value === true ? (selectedProductIds.value.length || 0) : '—'
  },
  {
    label: '账户默认继承',
    detail: '仍有商品跟随账号级策略，适合后续继续细分。',
    value: productsAvailable.value === true ? inheritedProductCount.value : '—'
  },
  {
    label: '全局覆盖比例',
    detail: '当前自动回复已覆盖当前范围内的商品占比。',
    value: coverageRate.value == null ? '—' : `${coverageRate.value}%`
  }
])

const accountCards = computed(() => {
  const scopeKnown = scopeAvailable.value === true
  const productsKnown = allProductsAvailable.value === true
  const cards = [
    {
      key: 'all',
      id: '',
      isAll: true,
      avatarUrl: '',
      active: selectedAccountId.value === '',
      badge: 'ALL',
      name: '全部账号',
      description: '汇总查看所有账号的自动回复覆盖情况',
      status: scopeKnown ? (globalEnabled.value ? '全局开启' : '全局关闭') : '状态未知',
      statusTone: scopeKnown ? (globalEnabled.value ? 'green' : 'gray') : 'amber',
      showMetrics: true,
      metrics: buildAccountMetrics(allProductsCache.value, productsKnown)
    }
  ]

  for (const account of accounts.value) {
    const accountProducts = scopedProductsForAccount(account.id)
    const enabledCount = accountProducts.filter(resolveProductEffective).length
    const inheritedCount = accountProducts.filter((product) => product.auto_reply_enabled == null && product.account_enabled === true).length
    const avatarUrl = brokenAvatarIds.value.has(account.id) ? '' : (account?.avatarUrl || '')

    const totalCount = accountProducts.length
    let statusText = scopeKnown && productsKnown ? '全部关闭' : '状态未知'
    let statusTone = 'gray'
    if (!scopeKnown || !productsKnown) {
      statusTone = 'amber'
    } else if (totalCount > 0 && enabledCount === totalCount) {
      statusText = '全部开启'
      statusTone = 'green'
    } else if (enabledCount > 0) {
      statusText = '部分开启'
      statusTone = 'amber'
    }

    cards.push({
      key: account.id,
      id: account.id,
      isAll: false,
      avatarUrl,
      active: selectedAccountId.value === account.id,
      badge: accountBadge(account),
      name: accountName(account),
      description: productsKnown
        ? `${accountProducts.length} 个商品 · ${enabledCount} 个已开启 · ${inheritedCount} 个继承账号级`
        : '商品基线状态未知，重新同步成功前禁止修改',
      status: statusText,
      statusTone,
      showMetrics: selectedAccountId.value === account.id,
      metrics: buildAccountMetrics(accountProducts, productsKnown)
    })
  }

  return cards
})

function onAvatarError(card) {
  if (!card?.id) return
  const next = new Set(brokenAvatarIds.value)
  next.add(card.id)
  brokenAvatarIds.value = next
}

function buildAccountMetrics(source, available = true) {
  if (!available) {
    return [
      { label: '商品总数', value: '—' },
      { label: '已开启', value: '—' },
      { label: '账号覆盖', value: '—' }
    ]
  }
  const list = Array.isArray(source) ? source : []
  return [
    { label: '商品总数', value: list.length || 0 },
    { label: '已开启', value: list.filter(resolveProductEffective).length || 0 },
    { label: '账号覆盖', value: list.length ? new Set(list.map((product) => product.accountId)).size : 0 }
  ]
}

function accountBadge(account) {
  const text = accountName(account)
  return text
    .replace(/[^\p{L}\p{N}]/gu, '')
    .slice(0, 2)
    .toUpperCase() || 'AC'
}

function scopedProductsForAccount(accountId) {
  if (!allProductsCache.value.length) {
    return accountId === selectedAccountId.value ? products.value : []
  }
  return allProductsCache.value.filter((product) => product.accountId === accountId)
}

function resolveProductEffective(product) {
  if (!product) return false
  if (product.auto_reply_enabled === 1) return true
  if (product.auto_reply_enabled === 0) return false
  return product.account_enabled === true || product.effective_enabled === true
}

function productPrimaryStatus(product) {
  if (product.auto_reply_enabled === 1) return { label: '已开启', tone: 'green' }
  if (product.auto_reply_enabled === 0) return { label: '已关闭', tone: 'gray' }
  if (product.account_enabled === true) return { label: '继承账号级', tone: 'blue' }
  return { label: '未开启', tone: 'gray' }
}

function productSecondaryStatus(product) {
  if (resolveProductEffective(product)) return { label: '配置启用', tone: 'blue' }
  if (product.auto_reply_enabled === 0) return { label: '待确认', tone: 'amber' }
  return null
}

function accountLabelForProduct(product) {
  const account = accounts.value.find((item) => item.id === product.accountId)
  return account ? accountName(account) : '未绑定账号'
}

function applyProductState(itemIds, enabled) {
  for (const source of [products.value, allProductsCache.value]) {
    source.forEach((product) => {
      if (itemIds.includes(product.id)) {
        product.auto_reply_enabled = enabled ? 1 : 0
        product.effective_enabled = enabled
      }
    })
  }
}

function hasRecordCollection(data) {
  if (Array.isArray(data)) return true
  if (!data || typeof data !== 'object') return false
  return ['records', 'list', 'rows', 'items', 'accounts'].some((key) => Array.isArray(data[key]))
}

function declaredTotalOf(data) {
  if (!data || typeof data !== 'object') return null
  const rawTotal = data.total ?? data.totalCount ?? data.count ?? data.pagination?.total
  if (rawTotal == null || !Number.isFinite(Number(rawTotal))) return null
  return totalOf(data, 0)
}

function productItemsOf(response) {
  const data = response?.data ?? response
  if (!data || typeof data !== 'object' || !Array.isArray(data.items)) {
    throw new Error('商品范围响应无效')
  }
  return data.items
}

async function loadAccounts() {
  const pageSize = 200
  accountsLoading.value = true
  accountsAvailable.value = false
  error.value = ''

  try {
    const collected = new Map()
    let current = 1
    let expectedTotal = null

    while (current <= 1000) {
      const response = await getAccounts({ current, size: pageSize })
      const data = response?.data ?? response
      const pageRecords = recordsOf(data)
      if (!hasRecordCollection(data) && pageRecords.length === 0) throw new Error('账号列表响应无效')

      const declaredTotal = declaredTotalOf(data)
      if (declaredTotal != null) expectedTotal = Math.max(expectedTotal ?? 0, declaredTotal)
      const sizeBefore = collected.size
      pageRecords.forEach((account) => {
        if (!account || account.id == null) throw new Error('账号列表包含无效记录')
        collected.set(String(account.id), account)
      })

      const reachedTotal = expectedTotal != null && collected.size >= expectedTotal
      if (reachedTotal || pageRecords.length === 0 || (expectedTotal == null && pageRecords.length < pageSize)) break
      if (collected.size === sizeBefore) throw new Error('账号分页未继续前进')
      current += 1
    }

    if (current > 1000) throw new Error('账号数量超过安全分页上限')
    if (expectedTotal != null && expectedTotal > collected.size) throw new Error(`账号列表不完整（应有 ${expectedTotal} 个，实际读取 ${collected.size} 个）`)

    accounts.value = Array.from(collected.values())
    if (selectedAccountId.value && !accounts.value.some((account) => account.id === selectedAccountId.value)) {
      selectedAccountId.value = ''
      selectedProductIds.value = []
    }
    accountsAvailable.value = true
    return true
  } catch (requestError) {
    accounts.value = []
    selectedAccountId.value = ''
    selectedProductIds.value = []
    accountsAvailable.value = false
    error.value = `账号加载失败：${friendlyError(requestError)}。当前不会使用不完整账号范围。`
    return false
  } finally {
    accountsLoading.value = false
  }
}

async function loadScopeStatus() {
  scopeLoading.value = true
  scopeAvailable.value = false
  try {
    const response = await getAutoReplyScopeStatus()
    const data = response?.data ?? response
    const validGlobal = data?.global_enabled === true || data?.global_enabled === false || data?.global_enabled === 1 || data?.global_enabled === 0
    if (!data || typeof data !== 'object' || !validGlobal || !data.account_scopes || typeof data.account_scopes !== 'object' || Array.isArray(data.account_scopes)) {
      throw new Error('作用域状态响应无效')
    }
    globalEnabled.value = data.global_enabled === true || data.global_enabled === 1
    accountScopeStatus.value = { ...data.account_scopes }
    scopeAvailable.value = true
    return true
  } catch (requestError) {
    globalEnabled.value = false
    accountScopeStatus.value = {}
    scopeAvailable.value = false
    if (import.meta.env.DEV) console.warn('[AutoReply] 加载作用域状态失败', requestError)
    return false
  } finally {
    scopeLoading.value = false
  }
}

async function loadAiCsSummary() {
  aiSummaryLoading.value = true
  aiSummaryAvailable.value = false
  try {
    const response = await getBusinessSettings('ai-customer-service')
    const data = response?.data ?? response
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('AI 客服摘要响应无效')
    aiCsSummary.value = data
    aiSummaryAvailable.value = true
    return true
  } catch (requestError) {
    aiCsSummary.value = null
    aiSummaryAvailable.value = false
    if (import.meta.env.DEV) console.warn('[AutoReply] 加载 AI 客服摘要失败', requestError)
    return false
  } finally {
    aiSummaryLoading.value = false
  }
}

async function loadAllProductsCache({ replaceVisible = false, requestVersion = productLoadVersion } = {}) {
  allProductsAvailable.value = false
  try {
    const response = await getAutoReplyScopeProducts()
    const items = productItemsOf(response)
    if (requestVersion !== productLoadVersion) return false
    allProductsCache.value = items
    allProductsAvailable.value = true
    if (replaceVisible) products.value = items
    return true
  } catch (requestError) {
    if (requestVersion === productLoadVersion) {
      allProductsCache.value = []
      allProductsAvailable.value = false
      if (replaceVisible) products.value = []
    }
    throw requestError
  }
}

async function loadProducts() {
  const requestVersion = ++productLoadVersion
  const accountId = selectedAccountId.value
  productsLoading.value = true
  productsAvailable.value = false
  selectedProductIds.value = []
  productVisibleLimit.value = 50

  try {
    if (accountId === '') {
      await loadAllProductsCache({ replaceVisible: true, requestVersion })
    } else {
      const response = await getAutoReplyScopeProducts(accountId)
      const items = productItemsOf(response)
      if (requestVersion !== productLoadVersion) return false
      products.value = items

      if (allProductsAvailable.value !== true) {
        try {
          await loadAllProductsCache({ requestVersion })
        } catch {
          // The visible account list remains readable, but writes stay locked without the all-product baseline.
        }
      }
    }

    if (requestVersion !== productLoadVersion) return false
    productsAvailable.value = true
    return true
  } catch (requestError) {
    if (requestVersion !== productLoadVersion) return false
    products.value = []
    productsAvailable.value = false
    if (accountId === '') {
      allProductsCache.value = []
      allProductsAvailable.value = false
    }
    error.value = `商品加载失败：${friendlyError(requestError)}。请求失败不会显示为空商品。`
    return false
  } finally {
    if (requestVersion === productLoadVersion) productsLoading.value = false
  }
}

function selectAccount(accountId) {
  if (accountsAvailable.value !== true || scopeUpdating.value || batchUpdating.value) return
  if (accountId && !accounts.value.some((account) => account.id === accountId)) return
  selectedAccountId.value = accountId
  selectedProductIds.value = []
  loadProducts()
}

function toggleProductSelect(productId) {
  if (productsAvailable.value !== true || scopeUpdating.value || batchUpdating.value) return
  const index = selectedProductIds.value.indexOf(productId)
  if (index >= 0) selectedProductIds.value.splice(index, 1)
  else selectedProductIds.value.push(productId)
}

const currentScopeEnabled = computed(() => {
  if (scopeAvailable.value !== true || productsAvailable.value !== true) return false
  if (selectedProductIds.value.length > 0) {
    return selectedProducts.value.length > 0 && selectedProducts.value.every(resolveProductEffective)
  }

  if (selectedAccount.value) return accountScopeStatus.value[selectedAccount.value.id] === true
  return globalEnabled.value
})

async function refreshCurrentScope() {
  if (isRefreshing.value || scopeUpdating.value || batchUpdating.value) return
  isRefreshing.value = true
  error.value = ''
  success.value = ''

  try {
    await loadAccounts()
    await Promise.all([
      loadScopeStatus(),
      loadAiCsSummary(),
      loadProducts()
    ])
  } finally {
    isRefreshing.value = false
  }
}

function restoreSwitchState(event) {
  if (event?.target) event.target.checked = currentScopeEnabled.value
}

function blockUnknownWrite(event) {
  restoreSwitchState(event)
  error.value = '自动回复配置状态未知，重新同步成功前禁止修改范围。'
}

function markWriteOutcomeUnknown(requestError, { scopeAffected = false } = {}) {
  products.value = []
  allProductsCache.value = []
  productsAvailable.value = false
  allProductsAvailable.value = false
  selectedProductIds.value = []
  if (scopeAffected) {
    scopeAvailable.value = false
    accountScopeStatus.value = {}
  }
  error.value = `操作结果未确认：${friendlyError(requestError, '网络错误')}。请先重新同步并核对实际状态，请勿直接重试。`
}

async function toggleCurrentScope(event) {
  if (scopeUpdating.value || batchUpdating.value) {
    restoreSwitchState(event)
    return
  }
  if (!scopeWritesAvailable.value) {
    blockUnknownWrite(event)
    return
  }

  const nextEnabled = !currentScopeEnabled.value
  const targetProductIds = [...selectedProductIds.value]
  const targetAccount = selectedAccount.value

  if (nextEnabled && !await ensureAiCustomerServiceEnabled()) {
    // The browser flips a native checkbox before the async confirmation resolves.
    // Restore its visual state when enabling was declined.
    if (event?.target) event.target.checked = currentScopeEnabled.value
    return
  }

  if (!targetProductIds.length && !targetAccount) {
    restoreSwitchState(event)
    const confirmed = await confirmAction({
      title: '全局主开关',
      description: '全局主开关需在「AI 客服配置」页面开启，是否前往？',
      confirmText: '前往配置'
    })
    if (confirmed) goToAiCsSettings()
    return
  }

  const accountMutation = targetProductIds.length === 0 && Boolean(targetAccount)
  scopeUpdating.value = true
  error.value = ''
  success.value = ''
  try {
    if (targetProductIds.length === 1) {
      const productId = targetProductIds[0]
      await updateProductAutoReplyScope(productId, nextEnabled)
      applyProductState([productId], nextEnabled)
      success.value = `已${nextEnabled ? '开启' : '关闭'}商品自动回复`
    } else if (targetProductIds.length > 1) {
      await batchUpdateAutoReplyScope({ itemIds: targetProductIds, enabled: nextEnabled })
      applyProductState(targetProductIds, nextEnabled)
      success.value = `已${nextEnabled ? '开启' : '关闭'} ${targetProductIds.length} 个商品`
    } else if (targetAccount) {
      await updateAccountAutoReplyScope(targetAccount.id, nextEnabled)
      accountScopeStatus.value[targetAccount.id] = nextEnabled
      success.value = `已${nextEnabled ? '开启' : '关闭'}该账号的自动回复`
    }
  } catch (requestError) {
    restoreSwitchState(event)
    markWriteOutcomeUnknown(requestError, { scopeAffected: accountMutation })
    return
  } finally {
    scopeUpdating.value = false
  }

  if (accountMutation) {
    const visibleReloaded = await loadProducts()
    let baselineReloaded
    try {
      baselineReloaded = await loadAllProductsCache({ requestVersion: productLoadVersion })
    } catch {
      baselineReloaded = false
    }
    if (!visibleReloaded || !baselineReloaded) {
      success.value = `账号开关已提交，但商品范围刷新不完整；重新同步成功前不会继续修改。`
    }
  }

  setTimeout(() => {
    success.value = ''
  }, 3000)
}

async function batchUpdateProducts(enabled) {
  if (batchUpdating.value || scopeUpdating.value || !selectedProductIds.value.length) return
  if (!scopeWritesAvailable.value) {
    blockUnknownWrite()
    return
  }
  if (enabled && !await ensureAiCustomerServiceEnabled()) return

  const itemIds = [...selectedProductIds.value]
  batchUpdating.value = true
  try {
    await batchUpdateAutoReplyScope({ itemIds, enabled })
    applyProductState(itemIds, enabled)
    success.value = `已${enabled ? '开启' : '关闭'} ${itemIds.length} 个商品`
    setTimeout(() => {
      success.value = ''
    }, 3000)
  } catch (requestError) {
    markWriteOutcomeUnknown(requestError)
  } finally {
    batchUpdating.value = false
  }
}

async function batchEnableAllProducts() {
  if (batchUpdating.value || scopeUpdating.value || !products.value.length) return
  if (!scopeWritesAvailable.value) {
    blockUnknownWrite()
    return
  }
  if (!await ensureAiCustomerServiceEnabled()) return

  const confirmed = await confirmAction({
    title: '一键全部开启',
    description: `将为当前列表的 ${products.value.length} 个商品全部开启自动回复，确认？`,
    confirmText: '确认开启'
  })
  if (!confirmed) return

  batchUpdating.value = true
  try {
    const itemIds = products.value.map((product) => product.id)
    await batchUpdateAutoReplyScope({ itemIds, enabled: true })
    applyProductState(itemIds, true)
    success.value = `已为 ${itemIds.length} 个商品开启自动回复`
    setTimeout(() => {
      success.value = ''
    }, 3000)
  } catch (requestError) {
    markWriteOutcomeUnknown(requestError)
  } finally {
    batchUpdating.value = false
  }
}

async function ensureAiCustomerServiceEnabled() {
  if (globalEnabled.value) return true
  const confirmed = await confirmAction({
    title: 'AI 客服尚未开启',
    description: '自动回复还需要先在「AI 客服配置」中开启主开关；当前操作不会生效。是否前往配置？',
    confirmText: '前往配置'
  })
  if (confirmed) goToAiCsSettings()
  return false
}

function goToAiCsSettings() {
  emit('navigate', 'settings-ai-cs')
}

onMounted(async () => {
  await loadAccounts()
  await Promise.all([
    loadScopeStatus(),
    loadAiCsSummary(),
    loadProducts()
  ])
})
</script>

<style scoped>
.auto-reply-shell {
  display: grid;
  gap: 18px;
}

.auto-reply-availability-notice {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0;
}

.auto-reply-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 392px;
  gap: 18px;
}

.auto-reply-hero-head {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
}

.auto-reply-hero-copy {
  min-width: 0;
}

.auto-reply-hero-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(47, 107, 255, 0.08);
  color: #3a63c6;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.auto-reply-hero-pill::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2f6bff, #59b3ff);
}

.auto-reply-hero-copy h1 {
  margin: 10px 0;
  font-size: 44px;
  line-height: 1;
  letter-spacing: -0.04em;
  color: #16315d;
}

.auto-reply-hero-copy p {
  max-width: 820px;
  margin: 0;
  color: #667b9f;
  font-size: 16px;
  line-height: 1.8;
}

.auto-reply-hero-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.auto-reply-action-button {
  min-height: 42px;
  border: 1px solid #dbe6f6;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  padding: 0 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #436289;
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 10px 24px rgba(42, 72, 130, 0.08);
}

.auto-reply-action-button.primary {
  border-color: transparent;
  color: #fff;
  background: linear-gradient(135deg, #2f6bff, #489cff);
  box-shadow: 0 16px 30px rgba(47, 107, 255, 0.24);
}

.auto-reply-action-button.full {
  width: 100%;
  justify-content: center;
}

.auto-reply-action-button:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.auto-reply-button-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.82;
}

.auto-reply-hero-main,
.auto-reply-hero-side,
.auto-reply-panel {
  border: 1px solid #e4ebf7;
  border-radius: 28px;
  overflow: hidden;
}

.auto-reply-hero-main {
  position: relative;
  padding: 26px 28px;
  background:
    radial-gradient(circle at 85% 20%, rgba(120, 195, 255, 0.28), transparent 18%),
    radial-gradient(circle at 70% 110%, rgba(20, 184, 166, 0.18), transparent 24%),
    linear-gradient(135deg, #173b74 0%, #2457b8 48%, #4d98ff 100%);
  color: #fff;
  box-shadow: 0 24px 42px rgba(32, 76, 177, 0.22);
}

.auto-reply-hero-main::before {
  content: '';
  position: absolute;
  width: 320px;
  height: 320px;
  right: -120px;
  top: -120px;
  border-radius: 48px;
  background: rgba(255, 255, 255, 0.08);
  transform: rotate(18deg);
}

.auto-reply-hero-main::after {
  content: '';
  position: absolute;
  width: 220px;
  height: 220px;
  right: 120px;
  bottom: -110px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.16);
}

.auto-reply-hero-kicker {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.auto-reply-hero-kicker::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7debd7;
  box-shadow: 0 0 0 4px rgba(125, 235, 215, 0.18);
}

.auto-reply-hero-main h2,
.auto-reply-hero-main p,
.auto-reply-hero-pill-row,
.auto-reply-hero-metrics {
  position: relative;
  z-index: 1;
}

.auto-reply-hero-main h2 {
  max-width: 760px;
  margin: 16px 0 14px;
  font-size: 34px;
  line-height: 1.15;
  letter-spacing: -0.04em;
}

.auto-reply-hero-main p {
  max-width: 780px;
  margin: 0 0 18px;
  color: rgba(255, 255, 255, 0.84);
  font-size: 15px;
  line-height: 1.8;
}

.auto-reply-hero-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 22px;
}

.auto-reply-hero-pill-row span {
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.18);
  font-size: 13px;
  font-weight: 700;
}

.auto-reply-hero-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  max-width: 760px;
}

.auto-reply-hero-metric {
  padding: 16px 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(6px);
}

.auto-reply-hero-metric b {
  display: block;
  margin-bottom: 6px;
  font-size: 26px;
  letter-spacing: -0.03em;
}

.auto-reply-hero-metric span {
  display: block;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.82);
}

.auto-reply-hero-side {
  padding: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 251, 255, 0.94));
  box-shadow: 0 18px 42px rgba(36, 67, 128, 0.1);
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.auto-reply-hero-side-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.auto-reply-hero-side-top h3 {
  margin: 0 0 8px;
  color: #6d83a7;
  font-size: 14px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.auto-reply-hero-side-top strong {
  white-space: pre-line;
  display: block;
  font-size: 30px;
  line-height: 1.06;
  letter-spacing: -0.04em;
  color: #16335f;
}

.auto-reply-side-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  width: fit-content;
  padding: 0 12px;
  border-radius: 999px;
  background: #edf4ff;
  color: #2f6bff;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-side-pill::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2f6bff, #59b3ff);
}

.auto-reply-side-note {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid #e5edf8;
  background: linear-gradient(135deg, #f7faff, #eef5ff);
}

.auto-reply-side-note strong {
  display: block;
  margin-bottom: 6px;
  color: #16335f;
  font-size: 14px;
}

.auto-reply-side-note p {
  margin: 0;
  color: #6c82a5;
  font-size: 13px;
  line-height: 1.72;
}

.auto-reply-side-list {
  display: grid;
  gap: 12px;
}

.auto-reply-side-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid #e8eef8;
  background: #fbfdff;
}

.auto-reply-side-item b {
  display: block;
  margin-bottom: 4px;
  color: #6e82a5;
  font-size: 13px;
}

.auto-reply-side-item strong {
  display: block;
  color: #17345f;
  font-size: 18px;
  letter-spacing: -0.02em;
}

.auto-reply-status-chip,
.auto-reply-status-pill,
.auto-reply-meta-badge,
.auto-reply-tiny-chip,
.auto-reply-insight-chip {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  white-space: nowrap;
}

.auto-reply-status-chip {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-status-chip.green,
.auto-reply-status-pill.green,
.auto-reply-meta-badge.green {
  background: #ecfdf3;
  color: #159c61;
}

.auto-reply-status-chip.blue,
.auto-reply-status-pill.blue,
.auto-reply-meta-badge.blue {
  background: #edf4ff;
  color: #2f6bff;
}

.auto-reply-status-chip.amber,
.auto-reply-meta-badge.amber {
  background: #fff6df;
  color: #d97706;
}

.auto-reply-status-chip.gray,
.auto-reply-status-pill.gray,
.auto-reply-meta-badge.gray {
  background: #f2f5f9;
  color: #7588a3;
}

.auto-reply-workspace {
  display: grid;
  grid-template-columns: 356px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.auto-reply-left-column,
.auto-reply-right-column,
.auto-reply-side-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.auto-reply-panel {
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 18px 42px rgba(36, 67, 128, 0.1);
}

.auto-reply-panel-head {
  padding: 20px 22px 16px;
  border-bottom: 1px solid #edf2fb;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.auto-reply-panel-head h3 {
  margin: 0 0 8px;
  font-size: 22px;
  letter-spacing: -0.02em;
  color: #18345f;
}

.auto-reply-panel-head p {
  margin: 0;
  color: #7d8fab;
  font-size: 13px;
  line-height: 1.7;
}

.auto-reply-tiny-chip {
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(47, 107, 255, 0.08);
  color: #3d66cb;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-panel-body {
  padding: 18px;
}

.auto-reply-account-list,
.auto-reply-product-list,
.auto-reply-summary-body,
.auto-reply-logic-body,
.auto-reply-impact-body {
  display: grid;
  gap: 12px;
}

.auto-reply-account-list {
  max-height: 540px;
  overflow: auto;
}

.auto-reply-account-item,
.auto-reply-product-item {
  width: 100%;
  text-align: left;
  border: 1px solid #e8eef8;
  background: #fbfdff;
  padding: 0;
}

.auto-reply-account-item {
  padding: 16px;
  border-radius: 20px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.auto-reply-account-item.active,
.auto-reply-product-item.selected {
  border-color: rgba(47, 107, 255, 0.28);
  background: linear-gradient(135deg, rgba(47, 107, 255, 0.12), rgba(12, 192, 223, 0.08));
  box-shadow: 0 14px 26px rgba(47, 107, 255, 0.12);
}

.auto-reply-account-item:disabled,
.auto-reply-product-item:disabled {
  cursor: not-allowed;
  opacity: .7;
}

.auto-reply-account-row,
.auto-reply-account-main {
  display: flex;
  align-items: center;
}

.auto-reply-account-row {
  justify-content: space-between;
  gap: 10px;
}

.auto-reply-account-main {
  gap: 12px;
  min-width: 0;
}

.auto-reply-account-badge {
  width: 42px;
  height: 42px;
  border-radius: 15px;
  display: grid;
  place-items: center;
  flex: none;
  color: #2f6bff;
  font-size: 13px;
  font-weight: 900;
  background: linear-gradient(135deg, rgba(47, 107, 255, 0.12), rgba(90, 174, 255, 0.14));
  overflow: hidden;
}

.auto-reply-account-badge.is-all {
  background: linear-gradient(135deg, #2f6bff 0%, #5aaeff 60%, #7debd7 100%);
  color: #fff;
  box-shadow: 0 8px 18px rgba(47, 107, 255, 0.28);
}

.auto-reply-account-icon {
  width: 24px;
  height: 24px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
}

.auto-reply-account-badge.has-avatar {
  background: linear-gradient(135deg, rgba(47, 107, 255, 0.18), rgba(125, 235, 215, 0.18));
  padding: 0;
}

.auto-reply-account-avatar {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 15px;
  display: block;
}

.auto-reply-account-main strong {
  display: block;
  margin-bottom: 4px;
  color: #17345f;
  font-size: 15px;
}

.auto-reply-account-main span {
  display: block;
  color: #7d8fab;
  font-size: 12px;
}

.auto-reply-status-pill {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-account-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.auto-reply-mini-stat {
  min-width: 92px;
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid #e9eff9;
}

.auto-reply-mini-stat b {
  display: block;
  margin-bottom: 4px;
  color: #18345f;
  font-size: 17px;
  letter-spacing: -0.02em;
}

.auto-reply-mini-stat span {
  display: block;
  color: #7f90ab;
  font-size: 11px;
}

.auto-reply-product-toolbar {
  padding: 0 18px 14px;
  display: grid;
  gap: 12px;
}

.auto-reply-search-row,
.auto-reply-filter-row,
.auto-reply-selection-actions,
.auto-reply-strategy-top {
  display: flex;
  gap: 10px;
}

.auto-reply-search-row {
  align-items: center;
}

.auto-reply-search {
  flex: 1;
  min-height: 44px;
  border: 1px solid #d9e4f4;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff, #f7faff);
  padding: 0 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.auto-reply-search input {
  width: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: #7084a7;
  font-size: 13px;
  font-weight: 600;
}

.auto-reply-search-icon {
  width: 14px;
  height: 14px;
  border: 2px solid #9ab0ce;
  border-radius: 50%;
  position: relative;
  flex: none;
}

.auto-reply-search-icon::after {
  content: '';
  position: absolute;
  width: 6px;
  height: 2px;
  right: -4px;
  bottom: -1px;
  background: #9ab0ce;
  transform: rotate(40deg);
  border-radius: 999px;
}

.auto-reply-filter-row {
  flex-wrap: wrap;
}

.auto-reply-filter-chip {
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid #dbe6f6;
  border-radius: 999px;
  background: #fff;
  color: #7387a5;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-filter-chip.active {
  background: #edf4ff;
  border-color: #cfe0ff;
  color: #2f6bff;
}

.auto-reply-filter-chip:disabled,
.auto-reply-search input:disabled {
  cursor: not-allowed;
  opacity: .62;
}

.auto-reply-loading,
.auto-reply-empty {
  padding: 24px 18px;
  color: #8294af;
  text-align: center;
  font-size: 13px;
}

.auto-reply-unavailable {
  display: grid;
  justify-items: center;
  gap: 8px;
  margin: 18px;
  padding: 22px 18px;
  border: 1px solid #f0d6a7;
  border-radius: 16px;
  background: #fffaf0;
  color: #846128;
  text-align: center;
  font-size: 13px;
  line-height: 1.65;
}

.auto-reply-unavailable strong {
  color: #6f4d18;
  font-size: 15px;
}

.auto-reply-unavailable .ghost {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid currentColor;
  border-radius: 10px;
  background: transparent;
  color: inherit;
  font-weight: 800;
  cursor: pointer;
}

.auto-reply-product-list {
  padding: 0 18px 18px;
  max-height: 680px;
  overflow: auto;
}

.auto-reply-load-more {
  padding: 8px 18px 16px;
  text-align: center;
}
.auto-reply-load-more .ghost {
  padding: 6px 16px;
  border: 1px dashed #c4cbd6;
  background: transparent;
  border-radius: 8px;
  color: #5b6b86;
  cursor: pointer;
  font-size: 12px;
  transition: all .2s;
}
.auto-reply-load-more .ghost:hover { border-color: var(--blue, #2563eb); color: var(--blue, #2563eb) }

.auto-reply-product-item {
  display: block;
  border-radius: 18px;
  padding: 14px;
}

.auto-reply-product-top {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.auto-reply-checkbox {
  width: 18px;
  height: 18px;
  border: 1.6px solid #b6c6dd;
  border-radius: 6px;
  margin-top: 2px;
  flex: none;
  background: #fff;
}

.auto-reply-checkbox.checked {
  position: relative;
  border-color: transparent;
  background: linear-gradient(135deg, #2f6bff, #5aaeff);
}

.auto-reply-checkbox.checked::after {
  content: '';
  position: absolute;
  left: 5px;
  top: 2px;
  width: 5px;
  height: 9px;
  border-right: 2px solid #fff;
  border-bottom: 2px solid #fff;
  transform: rotate(40deg);
}

.auto-reply-product-body {
  min-width: 0;
  flex: 1;
}

.auto-reply-product-body strong {
  display: block;
  margin-bottom: 8px;
  color: #17345f;
  font-size: 14px;
  line-height: 1.55;
}

.auto-reply-product-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.auto-reply-meta-badge {
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
}

.auto-reply-selection-bar {
  margin: 0 18px 18px;
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, #173b74, #306fff);
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  box-shadow: 0 18px 30px rgba(32, 76, 177, 0.2);
}

.auto-reply-selection-bar strong {
  display: block;
  margin-bottom: 4px;
  font-size: 14px;
}

.auto-reply-selection-bar span {
  display: block;
  color: rgba(255, 255, 255, 0.84);
  font-size: 12px;
  line-height: 1.7;
}

.auto-reply-selection-actions .ghost,
.auto-reply-selection-actions .fill {
  min-height: 34px;
  padding: 0 12px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-selection-actions .ghost {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}

.auto-reply-selection-actions .fill {
  border: 0;
  background: #fff;
  color: #245ad5;
}

.auto-reply-selection-actions button:disabled {
  opacity: 0.65;
}

.auto-reply-strategy-body,
.auto-reply-summary-body {
  gap: 16px;
}

.auto-reply-strategy-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px;
  align-items: start;
}

.auto-reply-strategy-copy h4 {
  margin: 0 0 10px;
  color: #18345f;
  font-size: 30px;
  line-height: 1.1;
  letter-spacing: -0.04em;
}

.auto-reply-strategy-copy p {
  margin: 0 0 16px;
  color: #6f83a5;
  font-size: 14px;
  line-height: 1.8;
}

.auto-reply-insight-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.auto-reply-insight-chip {
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid #e5edf8;
  background: #f7fbff;
  color: #57729e;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-toggle-box {
  padding: 14px;
  border-radius: 20px;
  border: 1px solid #dfebff;
  background: linear-gradient(135deg, #edf4ff, #f8fbff);
  display: grid;
  place-items: center;
  gap: 8px;
  text-align: center;
}

.auto-reply-toggle-box b {
  color: #6e83a6;
  font-size: 12px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.auto-reply-toggle-box strong {
  color: #17345f;
  font-size: 14px;
}

.auto-reply-switch {
  position: relative;
  width: 42px;
  height: 24px;
  display: inline-block;
  flex: none;
}

.auto-reply-switch-large {
  width: 56px;
  height: 30px;
}

.auto-reply-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.auto-reply-slider {
  position: absolute;
  inset: 0;
  cursor: pointer;
  border-radius: 999px;
  background: #cbd5e1;
  transition: 0.2s;
}

.auto-reply-slider::before {
  content: '';
  position: absolute;
  left: 3px;
  top: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 8px 16px rgba(26, 76, 166, 0.18);
  transition: 0.2s;
}

.auto-reply-switch-large .auto-reply-slider::before {
  width: 24px;
  height: 24px;
}

.auto-reply-switch input:checked + .auto-reply-slider {
  background: linear-gradient(90deg, #2f6bff, #54a6ff);
}

.auto-reply-switch input:checked + .auto-reply-slider::before {
  transform: translateX(18px);
}

.auto-reply-switch-large input:checked + .auto-reply-slider::before {
  transform: translateX(26px);
}

.auto-reply-metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.auto-reply-metric-card {
  min-height: 116px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid #e7eef8;
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  box-shadow: 0 10px 24px rgba(42, 72, 130, 0.08);
}

.auto-reply-metric-card b {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  margin-bottom: 16px;
  font-size: 12px;
  font-weight: 800;
}

.auto-reply-metric-card b.blue {
  background: #edf4ff;
  color: #2f6bff;
}

.auto-reply-metric-card b.green {
  background: #ecfdf3;
  color: #159c61;
}

.auto-reply-metric-card b.amber {
  background: #fff6df;
  color: #d97706;
}

.auto-reply-metric-card strong {
  display: block;
  margin-bottom: 8px;
  color: #17325d;
  font-size: 28px;
  line-height: 1;
  letter-spacing: -0.04em;
}

.auto-reply-metric-card span {
  display: block;
  color: #6f83a5;
  font-size: 13px;
  line-height: 1.6;
}

.auto-reply-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 18px;
  align-items: start;
}

.auto-reply-summary-block {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid #e7eef8;
  background: linear-gradient(180deg, #ffffff, #f9fbff);
}

.auto-reply-summary-block label {
  display: block;
  margin-bottom: 8px;
  color: #7187aa;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.auto-reply-summary-block p {
  margin: 0;
  color: #29476f;
  font-size: 14px;
  line-height: 1.8;
}

.auto-reply-summary-footer {
  padding: 0 18px 18px;
}

.auto-reply-logic-step {
  position: relative;
  padding: 14px 14px 14px 52px;
  border-radius: 18px;
  border: 1px solid #e7eef8;
  background: linear-gradient(180deg, #ffffff, #f9fbff);
}

.auto-reply-logic-step::before {
  content: attr(data-step);
  position: absolute;
  left: 14px;
  top: 14px;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #2f6bff, #5aaeff);
  color: #fff;
  font-size: 12px;
  font-weight: 900;
  box-shadow: 0 10px 18px rgba(47, 107, 255, 0.2);
}

.auto-reply-logic-step strong {
  display: block;
  margin-bottom: 6px;
  color: #17345f;
  font-size: 14px;
}

.auto-reply-logic-step span,
.auto-reply-impact-row span,
.auto-reply-impact-note {
  color: #7286a7;
  font-size: 12px;
  line-height: 1.7;
}

.auto-reply-impact-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid #e7eef8;
  background: linear-gradient(180deg, #ffffff, #f9fbff);
}

.auto-reply-impact-row strong {
  display: block;
  margin-bottom: 4px;
  color: #17345f;
  font-size: 14px;
}

.auto-reply-impact-value {
  flex: none;
  color: #17345f;
  font-size: 24px;
  font-weight: 900;
  letter-spacing: -0.04em;
}

.auto-reply-impact-note {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(20, 184, 166, 0.14);
  background: linear-gradient(135deg, rgba(20, 184, 166, 0.08), rgba(47, 107, 255, 0.06));
  color: #2a5b79;
}

.auto-reply-impact-note strong {
  display: block;
  margin-bottom: 6px;
  color: #17345f;
  font-size: 14px;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
}

@media (max-width: 1800px) {
  .auto-reply-detail-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .auto-reply-side-stack {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
}

@media (max-width: 1480px) {
  .auto-reply-hero,
  .auto-reply-workspace {
    grid-template-columns: minmax(0, 1fr);
  }

  .auto-reply-strategy-top,
  .auto-reply-metric-grid,
  .auto-reply-hero-metrics {
    grid-template-columns: minmax(0, 1fr);
  }

  .auto-reply-side-stack {
    grid-template-columns: minmax(0, 1fr);
  }

  /* 网格子元素防止溢出 */
  .auto-reply-detail-grid > *,
  .auto-reply-side-stack > *,
  .auto-reply-hero > *,
  .auto-reply-workspace > *,
  .auto-reply-strategy-top > *,
  .auto-reply-metric-grid > *,
  .auto-reply-hero-metrics > * {
    min-width: 0;
  }
}

@media (max-width: 1120px) {
  .auto-reply-hero-head,
  .auto-reply-search-row,
  .auto-reply-selection-bar,
  .auto-reply-hero-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .auto-reply-selection-actions {
    width: 100%;
  }

  .auto-reply-selection-actions .ghost,
  .auto-reply-selection-actions .fill {
    justify-content: center;
    flex: 1;
  }
}

/* ===== 移动端响应式 (max-width: 900px) ===== */
@media (max-width: 900px) {
  /* 整体外壳间距收敛 */
  .auto-reply-shell {
    gap: 12px;
  }

  /* Hero 主区/侧栏圆角收敛 */
  .auto-reply-hero-main,
  .auto-reply-hero-side,
  .auto-reply-panel {
    border-radius: 16px;
  }

  /* Hero 主区内边距 + 大字号收敛 */
  .auto-reply-hero-main {
    padding: 14px;
  }

  .auto-reply-hero-copy h1 {
    font-size: 22px;
    margin: 8px 0;
  }

  .auto-reply-hero-copy p {
    font-size: 13px;
    line-height: 1.7;
  }

  .auto-reply-hero-main h2 {
    font-size: 20px;
    margin: 12px 0 10px;
    line-height: 1.25;
  }

  .auto-reply-hero-main p {
    font-size: 13px;
    line-height: 1.7;
    margin-bottom: 14px;
  }

  .auto-reply-hero-pill-row {
    gap: 8px;
    margin-bottom: 14px;
  }

  .auto-reply-hero-pill-row span {
    min-height: 28px;
    padding: 0 10px;
    font-size: 12px;
  }

  /* Hero 指标卡：单列 + 收敛 */
  .auto-reply-hero-metric {
    padding: 12px;
    border-radius: 14px;
  }

  .auto-reply-hero-metric b {
    font-size: 20px;
    margin-bottom: 4px;
  }

  .auto-reply-hero-metric span {
    font-size: 11px;
    line-height: 1.55;
  }

  /* 侧栏内边距 + 大字号收敛 */
  .auto-reply-hero-side {
    padding: 14px;
    gap: 12px;
  }

  .auto-reply-hero-side-top strong {
    font-size: 20px;
    line-height: 1.15;
  }

  .auto-reply-side-note {
    padding: 12px;
    border-radius: 14px;
  }

  .auto-reply-side-note p {
    font-size: 12px;
    line-height: 1.65;
  }

  .auto-reply-side-item {
    padding: 10px 12px;
    border-radius: 14px;
    gap: 10px;
  }

  .auto-reply-side-item strong {
    font-size: 15px;
  }

  .auto-reply-side-item b {
    font-size: 12px;
  }

  /* 工作台左右列间距收敛 */
  .auto-reply-left-column,
  .auto-reply-right-column,
  .auto-reply-side-stack {
    gap: 12px;
  }

  /* 面板头/体内边距收敛 */
  .auto-reply-panel-head {
    padding: 14px 14px 12px;
    gap: 10px;
  }

  .auto-reply-panel-head h3 {
    font-size: 18px;
    margin-bottom: 6px;
  }

  .auto-reply-panel-head p {
    font-size: 12px;
    line-height: 1.6;
  }

  .auto-reply-panel-body {
    padding: 12px;
  }

  /* 账号列表项收敛 */
  .auto-reply-account-item {
    padding: 12px;
    border-radius: 14px;
  }

  .auto-reply-account-row {
    gap: 8px;
  }

  .auto-reply-account-main {
    gap: 10px;
  }

  .auto-reply-account-badge {
    width: 36px;
    height: 36px;
    border-radius: 12px;
    font-size: 12px;
  }

  .auto-reply-account-main strong {
    font-size: 14px;
    margin-bottom: 2px;
  }

  .auto-reply-account-main span {
    font-size: 11px;
    line-height: 1.5;
  }

  .auto-reply-account-stats {
    gap: 6px;
    margin-top: 10px;
  }

  .auto-reply-mini-stat {
    min-width: 0;
    flex: 1 1 calc(33.3% - 6px);
    padding: 8px 10px;
    border-radius: 12px;
  }

  .auto-reply-mini-stat b {
    font-size: 15px;
    margin-bottom: 2px;
  }

  .auto-reply-mini-stat span {
    font-size: 10px;
  }

  /* 账号列表横向滚动顺畅 */
  .auto-reply-account-list {
    max-height: 460px;
    -webkit-overflow-scrolling: touch;
  }

  /* 商品工具栏收敛 */
  .auto-reply-product-toolbar {
    padding: 0 12px 10px;
    gap: 10px;
  }

  .auto-reply-search {
    min-height: 40px;
    border-radius: 12px;
  }

  .auto-reply-search input {
    font-size: 13px;
  }

  .auto-reply-action-button {
    min-height: 40px;
    padding: 0 14px;
    font-size: 13px;
    border-radius: 12px;
  }

  .auto-reply-filter-row {
    gap: 8px;
  }

  .auto-reply-filter-chip {
    min-height: 30px;
    padding: 0 10px;
    font-size: 11px;
  }

  /* 商品列表收敛 */
  .auto-reply-product-list {
    padding: 0 12px 12px;
    max-height: 600px;
    -webkit-overflow-scrolling: touch;
  }

  .auto-reply-product-item {
    padding: 10px;
    border-radius: 14px;
  }

  .auto-reply-product-top {
    gap: 10px;
  }

  .auto-reply-product-body strong {
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 6px;
  }

  .auto-reply-product-meta {
    gap: 6px;
  }

  .auto-reply-meta-badge {
    min-height: 22px;
    padding: 0 8px;
    font-size: 10px;
  }

  /* 选择吸附条收敛 */
  .auto-reply-selection-bar {
    margin: 0 12px 12px;
    padding: 12px;
    border-radius: 14px;
    gap: 10px;
  }

  .auto-reply-selection-bar strong {
    font-size: 13px;
  }

  .auto-reply-selection-bar span {
    font-size: 11px;
    line-height: 1.6;
  }

  .auto-reply-selection-actions .ghost,
  .auto-reply-selection-actions .fill {
    min-height: 38px;
    padding: 0 12px;
  }

  /* 策略卡大字号收敛 */
  .auto-reply-strategy-copy h4 {
    font-size: 18px;
    line-height: 1.25;
    margin-bottom: 8px;
  }

  .auto-reply-strategy-copy p {
    font-size: 13px;
    line-height: 1.7;
    margin-bottom: 12px;
  }

  .auto-reply-insight-chip {
    min-height: 28px;
    padding: 0 10px;
    font-size: 11px;
  }

  .auto-reply-toggle-box {
    padding: 10px;
    border-radius: 14px;
  }

  .auto-reply-toggle-box strong {
    font-size: 13px;
  }

  /* 指标卡收敛 */
  .auto-reply-metric-card {
    min-height: 0;
    padding: 12px;
    border-radius: 14px;
  }

  .auto-reply-metric-card b {
    min-height: 24px;
    padding: 0 8px;
    margin-bottom: 10px;
    font-size: 11px;
  }

  .auto-reply-metric-card strong {
    font-size: 22px;
    margin-bottom: 6px;
  }

  .auto-reply-metric-card span {
    font-size: 12px;
    line-height: 1.55;
  }

  /* 详情区收敛 */
  .auto-reply-detail-grid {
    gap: 12px;
  }

  .auto-reply-summary-block {
    padding: 12px;
    border-radius: 14px;
  }

  .auto-reply-summary-block label {
    font-size: 11px;
    margin-bottom: 6px;
  }

  .auto-reply-summary-block p {
    font-size: 13px;
    line-height: 1.7;
  }

  .auto-reply-summary-footer {
    padding: 0 12px 12px;
  }

  /* 生效逻辑步骤收敛 */
  .auto-reply-logic-step {
    padding: 10px 10px 10px 44px;
    border-radius: 14px;
  }

  .auto-reply-logic-step::before {
    left: 10px;
    top: 10px;
    width: 24px;
    height: 24px;
    font-size: 11px;
  }

  .auto-reply-logic-step strong {
    font-size: 13px;
    margin-bottom: 4px;
  }

  .auto-reply-logic-step span {
    font-size: 11px;
    line-height: 1.6;
  }

  /* 影响面行：横向 → 纵向堆叠 */
  .auto-reply-impact-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 10px 12px;
    border-radius: 14px;
  }

  .auto-reply-impact-row strong {
    font-size: 13px;
    margin-bottom: 2px;
  }

  .auto-reply-impact-row span {
    font-size: 11px;
    line-height: 1.6;
  }

  .auto-reply-impact-value {
    font-size: 20px;
    align-self: flex-end;
  }

  .auto-reply-impact-note {
    padding: 10px 12px;
    border-radius: 14px;
    font-size: 11px;
    line-height: 1.65;
  }

  .auto-reply-impact-note strong {
    font-size: 13px;
    margin-bottom: 4px;
  }

  /* tiny-chip 收敛 */
  .auto-reply-tiny-chip {
    min-height: 26px;
    padding: 0 10px;
    font-size: 11px;
  }

  /* 加载更多按钮收敛 */
  .auto-reply-load-more {
    padding: 6px 12px 12px;
  }
}
</style>
