<template>
  <div class="model-settings-page">
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <section class="page-hero">
      <div class="page-hero-copy">
        <span class="page-pill">General Model</span>
        <h1>模型配置</h1>
        <p>通用模型用于接待回复、文本生成、商品改写等场景。向量模型（Embedding）已拆分到独立页签维护，避免混填。</p>

        <div class="page-actions">
          <AppButton type="primary" :loading="saving" :disabled="!configAvailable" @click="save">保存配置</AppButton>
          <AppButton :loading="loading" @click="loadPage">重新加载</AppButton>
        </div>
      </div>

      <div class="hero-badges">
        <div class="status-card" :class="runtimeStatusAvailable && runtimeStatus.generalModelConfigured ? 'green' : 'orange'">
          <span>通用模型</span>
          <strong>{{ runtimeStatusAvailable ? (runtimeStatus.generalModelConfigured ? '已配置' : '未设置') : '状态未知' }}</strong>
          <small>对话 / 改写 / 文本生成</small>
        </div>
      </div>
    </section>

    <div class="page-grid">
      <CardPanel title="通用模型" desc="所有通用 AI 调用都会优先读取这里的配置。建议按照“供应商 → 模型名 → 地址 → Key”的顺序填写。">
        <div class="config-overview">
          <article class="overview-card">
            <span>适用场景</span>
            <strong>客服对话、商品润色、文本生成统一走这里</strong>
            <p>如果你的系统里多个功能都依赖同一套通用大模型，那么它们都会共享这组配置。</p>
          </article>
          <article class="overview-card">
            <span>填写原则</span>
            <strong>优先保证可调用，再处理别名与策略配置</strong>
            <p>先把最基础的供应商、模型名、接口地址和 API Key 填对，再补超时、润色策略等增强参数。</p>
          </article>
        </div>

        <div class="field-grid two">
          <AdminConfigField
            label="模型供应商"
            hint="用于标记你当前接入的是哪家服务，方便后续联调与排查。"
            meta="直接从下拉列表中选择供应商即可，无需手动输入。若列表中没有你使用的供应商，可选择“其他 / 自定义”。"
            badge="第一步"
            required
          >
            <select v-model="form.generalModel.provider" class="config-input config-select">
              <option value="" disabled>请选择供应商</option>
              <option v-for="p in providerOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
              <option :value="CUSTOM_PROVIDER_VALUE">其他 / 自定义</option>
            </select>
            <input
              v-if="isCustomProvider"
              v-model="customProvider"
              class="config-input custom-provider-input"
              placeholder="输入自定义供应商标识，例如：azure"
            />
          </AdminConfigField>

          <AdminConfigField
            label="模型名称"
            hint="系统默认会按这个名称发起调用，建议填写对外使用的标准模型名。"
            meta="示例：gpt-4o-mini。若你使用代理网关，这里通常填写网关要求的模型字段。"
            badge="核心参数"
            required
          >
            <input v-model="form.generalModel.modelName" class="config-input" :placeholder="config.generalModel.modelName || 'gpt-4o-mini'" />
          </AdminConfigField>

          <AdminConfigField
            label="接口地址"
            hint="仅支持可解析的公网 HTTPS OpenAI 兼容根地址；系统会拒绝明文 HTTP、本机、内网、重定向与代理环境。"
            meta="大多数服务以 /v1 结尾。切换到不同主机时必须同时重新输入 API Key，避免把已保存密钥发送到新地址。"
            badge="第二步"
            required
          >
            <input v-model="form.generalModel.baseUrl" class="config-input" :placeholder="config.generalModel.baseUrl || 'https://api.openai.com/v1'" />
          </AdminConfigField>

          <AdminConfigField
            label="API Key"
            hint="用于实际鉴权。保存后不会回显完整内容，只显示已保存状态。"
            meta="Key 轮换时直接覆盖即可；修改接口主机时也必须重新输入。若报 401/403，请检查 Key 与地址是否匹配。"
            badge="第三步"
            required
          >
              <SecretInput
              v-model="form.generalModel.apiKey"
              :placeholder="config.generalModel.apiKeyConfigured ? '已保存，直接输入新值可覆盖' : 'sk-...'"
              autocomplete="off"
            />
          </AdminConfigField>

          <AdminConfigField
            label="请求超时（秒）"
            hint="控制调用等待时长，过短会导致长回复或网络抖动时更容易失败。"
            meta="建议从 15 秒起步；如果模型回复较长或服务在海外，可适当提高到 30~60 秒。"
            badge="稳定性"
          >
            <input v-model.number="form.generalModel.requestTimeout" class="config-input" type="number" min="1" max="300" :placeholder="config.generalModel.requestTimeout ? String(config.generalModel.requestTimeout) : '15'" />
          </AdminConfigField>

          <AdminConfigField
            label="润色关键词"
            hint="命中这些词时，系统更倾向走润色、改写或优化描述的处理逻辑。"
            meta="支持逗号、顿号或换行分隔，适合填写“润色、改写、优化标题、增强卖点”等策略词。"
            badge="策略增强"
            wide
          >
            <textarea
              v-model="form.generalModel.polishKeywords"
              class="config-textarea"
              rows="3"
              :placeholder="config.generalModel.polishKeywords || '使用逗号、顿号或换行分隔'"
            />
          </AdminConfigField>

          <AdminConfigField
            label="禁止润色关键词"
            hint="命中这些词时跳过润色，避免把需要原样输出的内容误改写。"
            meta="适合放退款、投诉、售后等敏感语境，确保客服回复或记录类文本保持原意。"
            badge="风险控制"
            wide
          >
            <textarea
              v-model="form.generalModel.polishForbiddenKeywords"
              class="config-textarea"
              rows="3"
              :placeholder="config.generalModel.polishForbiddenKeywords || '使用逗号、顿号或换行分隔'"
            />
          </AdminConfigField>
        </div>
      </CardPanel>

      <CardPanel title="配置建议" desc="下面这些说明可以帮助你更快判断“应该填什么”，也能减少联调时的来回试错。">
        <div class="guide-grid">
          <article class="guide-card">
            <div class="guide-icon">A</div>
            <div>
              <strong>优先保证基础调用通</strong>
              <p>先确保模型名、接口地址和 API Key 可以正常返回结果，再去优化策略与超时参数。</p>
            </div>
          </article>
          <article class="guide-card">
            <div class="guide-icon">B</div>
            <div>
              <strong>代理网关要看兼容协议</strong>
              <p>如果你不是直连官方接口，而是使用中转服务，模型名和地址请以中转服务文档为准。</p>
            </div>
          </article>
          <article class="guide-card">
            <div class="guide-icon">C</div>
            <div>
              <strong>润色词只做策略提示</strong>
              <p>它们不会替代模型能力本身，更适合用来区分不同业务语境下的回复处理方式。</p>
            </div>
          </article>
        </div>

        <ul class="hint-list">
          <li>通用模型负责站内大部分文本生成能力，和向量模型（Embedding）不是同一个用途。</li>
          <li>如果保存后仍报错，先检查接口地址是否正确、模型名是否被服务端支持、Key 是否和当前供应商匹配。</li>
          <li>如使用代理网关，请直接在“模型名称”中填写网关要求的模型字段，避免同一配置出现两个名称。</li>
          <li>建议为生产环境单独准备一套 API Key，避免与个人测试或其他项目混用，降低排查成本。</li>
        </ul>
      </CardPanel>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import AdminConfigField from '../../components/AdminConfigField.vue'
import AppButton from '../../components/AppButton.vue'
import CardPanel from '../../components/CardPanel.vue'
import SecretInput from '../../components/SecretInput.vue'
import {
  cloneOpenSourceConfig,
  useOpenSourceSettings,
} from '../../composables/useOpenSourceSettings.js'

defineProps({ active: String })

const {
  loading,
  saving,
  error,
  success,
  config,
  runtimeStatus,
  configAvailable,
  runtimeStatusAvailable,
  loadBundle,
  refreshRuntimeStatus,
  saveConfig,
} = useOpenSourceSettings()

// 供应商下拉选项：预置常见厂商 + “其他 / 自定义”
const CUSTOM_PROVIDER_VALUE = '__custom__'
const PROVIDER_PRESETS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek 深度求索' },
  { value: 'qwen', label: '通义千问 Qwen' },
  { value: 'moonshot', label: 'Moonshot 月之暗面 (Kimi)' },
  { value: 'zhipu', label: '智谱 GLM' },
  { value: 'doubao', label: '豆包 Doubao' },
  { value: 'baichuan', label: 'Baichuan 百川' },
  { value: 'minimax', label: 'MiniMax' },
  { value: 'yi', label: '零一万物 Yi' },
  { value: 'stepfun', label: '阶跃星辰 Step' },
  { value: 'siliconflow', label: 'SiliconFlow 硅基流动' },
  { value: 'openrouter', label: 'OpenRouter' },
]

const customProvider = ref('')

// 已保存但不在预置列表中的供应商，作为单独一项展示，避免丢失原值
const providerOptions = computed(() => {
  const list = [...PROVIDER_PRESETS]
  const current = (config.generalModel?.provider || '').trim()
  if (
    current &&
    current !== CUSTOM_PROVIDER_VALUE &&
    !PROVIDER_PRESETS.some((p) => p.value === current)
  ) {
    list.push({ value: current, label: `自定义：${current}` })
  }
  return list
})

const isCustomProvider = computed(
  () => form.generalModel.provider === CUSTOM_PROVIDER_VALUE
)

const form = reactive({
  generalModel: {
    provider: '',
    modelName: '',
    baseUrl: '',
    apiKey: '',
    requestTimeout: null,
    polishKeywords: '',
    polishForbiddenKeywords: '',
  },
})

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  loadPage()
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-header-action', onHeaderAction)
})

// 仅回填下拉选择项；文本类输入保持为空，已保存值通过 placeholder 以提示文字形式展示，
// 用户选中输入框后可直接输入新值，无需先删除原有内容。
function syncForm() {
  const g = config.generalModel || {}
  const savedProvider = (g.provider || '').trim()
  if (savedProvider && !PROVIDER_PRESETS.some((p) => p.value === savedProvider)) {
    form.generalModel.provider = CUSTOM_PROVIDER_VALUE
    customProvider.value = savedProvider
  } else {
    form.generalModel.provider = savedProvider
    customProvider.value = ''
  }
  form.generalModel.modelName = ''
  form.generalModel.baseUrl = ''
  form.generalModel.apiKey = ''
  form.generalModel.requestTimeout = null
  form.generalModel.polishKeywords = ''
  form.generalModel.polishForbiddenKeywords = ''
}

async function loadPage() {
  await loadBundle({ includeRuntimeStatus: true })
  if (configAvailable.value) syncForm()
}

// 留空的字段回退到已保存值，避免误清空配置；输入了新值则覆盖。
function pickNext(next, old) {
  const n = (next == null ? '' : String(next)).trim()
  return n || (old == null ? '' : String(old)).trim()
}

async function save() {
  if (!configAvailable.value) return
  const prev = config.generalModel || {}
  let provider = (form.generalModel.provider || '').trim()
  if (provider === CUSTOM_PROVIDER_VALUE) {
    provider = customProvider.value.trim() || (prev.provider || '').trim()
  }
  if (!provider) provider = (prev.provider || '').trim()

  const payload = cloneOpenSourceConfig(config)
  payload.generalModel = {
    provider,
    modelName: pickNext(form.generalModel.modelName, prev.modelName),
    baseUrl: pickNext(form.generalModel.baseUrl, prev.baseUrl),
    apiKey: pickNext(form.generalModel.apiKey, prev.apiKey),
    requestTimeout:
      Number(form.generalModel.requestTimeout) ||
      Number(prev.requestTimeout) ||
      15,
    polishKeywords: pickNext(form.generalModel.polishKeywords, prev.polishKeywords),
    polishForbiddenKeywords: pickNext(
      form.generalModel.polishForbiddenKeywords,
      prev.polishForbiddenKeywords
    ),
  }
  const saved = await saveConfig(payload, { successMessage: '通用模型配置已保存' })
  if (!saved) return
  syncForm()
  await refreshRuntimeStatus()
}

function onHeaderAction(event) {
  if (event.detail === 'settings-save') save()
  if (event.detail === 'settings-reload') loadPage()
}
</script>

<style scoped>
.model-settings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  padding: 22px;
  border-radius: 24px;
  border: 1px solid rgba(231, 237, 247, 0.95);
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.12), transparent 32%),
    radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 35%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 251, 255, 0.92));
  box-shadow: 0 18px 42px rgba(31, 53, 94, 0.08);
}

.page-pill {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: #2c63d4;
  font-size: 11px;
  font-weight: 800;
}

.page-hero-copy h1 {
  margin: 10px 0 0;
  font-size: 28px;
  color: #13213d;
}

.page-hero-copy p {
  margin: 10px 0 0;
  max-width: 760px;
  line-height: 1.8;
  color: #60738e;
}

.page-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

.hero-badges {
  display: grid;
  gap: 12px;
}

.status-card {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid rgba(231, 237, 247, 0.95);
}

.status-card span {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #7a879e;
}

.status-card strong {
  display: block;
  margin-top: 8px;
  font-size: 20px;
  color: #13213d;
}

.status-card small {
  display: block;
  margin-top: 6px;
  line-height: 1.65;
  color: #667892;
}

.status-card.green {
  background: linear-gradient(180deg, rgba(236, 253, 243, 0.98), rgba(255, 255, 255, 0.96));
}

.status-card.orange {
  background: linear-gradient(180deg, rgba(255, 248, 237, 0.98), rgba(255, 255, 255, 0.96));
}

.page-grid {
  display: grid;
  gap: 16px;
}

.config-overview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.overview-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(225, 233, 245, 0.98);
  background: linear-gradient(135deg, #fbfdff, #f5f9ff);
}

.overview-card span {
  display: inline-flex;
  min-height: 22px;
  align-items: center;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(13, 107, 255, 0.08);
  color: #2c63d4;
  font-size: 11px;
  font-weight: 800;
}

.overview-card strong {
  display: block;
  margin-top: 12px;
  color: #13213d;
  font-size: 15px;
}

.overview-card p {
  margin: 8px 0 0;
  color: #6e7e98;
  line-height: 1.7;
  font-size: 13px;
}

.field-grid {
  display: grid;
  gap: 14px;
}

.field-grid.two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

/* 下拉选择框：在通用输入样式基础上增加右侧箭头，原生外观更统一 */
:deep(.config-select) {
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  padding-right: 38px;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%237a879e' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'></polyline></svg>");
  background-repeat: no-repeat;
  background-position: right 14px center;
  background-color: #fff;
  cursor: pointer;
}

/* “其他 / 自定义”时展开的自定义输入框，与下拉框形成层级关系 */
.custom-provider-input {
  margin-top: 10px;
}

.guide-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.guide-card {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(225, 233, 245, 0.98);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 251, 255, 0.95));
}

.guide-icon {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  background: #edf4ff;
  color: #0d6bff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 800;
}

.guide-card strong {
  display: block;
  color: #13213d;
  font-size: 14px;
}

.guide-card p {
  margin: 6px 0 0;
  color: #6d7c96;
  line-height: 1.7;
  font-size: 12.5px;
}

.hint-list {
  margin: 0;
  padding-left: 18px;
  color: #667892;
  line-height: 1.8;
}

.hint-list li + li {
  margin-top: 4px;
}

@media (max-width: 1180px) {
  .page-hero,
  .config-overview,
  .guide-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 920px) {
  .field-grid.two {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .model-settings-page {
    gap: 12px;
  }

  .page-hero {
    grid-template-columns: minmax(0, 1fr);
    padding: 14px;
    border-radius: 16px;
  }

  .page-hero-copy h1 {
    font-size: 20px;
  }

  .page-hero-copy p {
    font-size: 13px;
    line-height: 1.6;
  }

  .page-actions {
    gap: 8px;
    margin-top: 12px;
  }

  .hero-badges {
    gap: 10px;
  }

  .status-card {
    padding: 12px;
    border-radius: 14px;
  }

  .status-card strong {
    font-size: 16px;
  }

  .status-card small {
    font-size: 12px;
  }

  .page-grid {
    gap: 12px;
  }

  .config-overview {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
    margin-bottom: 12px;
  }

  .overview-card {
    padding: 12px;
    border-radius: 14px;
  }

  .overview-card strong {
    margin-top: 8px;
    font-size: 14px;
  }

  .overview-card p {
    margin-top: 6px;
    font-size: 12.5px;
    line-height: 1.6;
  }

  .field-grid {
    gap: 12px;
  }

  .field-grid.two {
    grid-template-columns: minmax(0, 1fr);
  }

  .guide-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
    margin-bottom: 12px;
  }

  .page-hero > *,
  .config-overview > *,
  .guide-grid > *,
  .field-grid.two > * {
    min-width: 0;
  }

  .guide-card {
    padding: 12px;
    border-radius: 14px;
    gap: 10px;
  }

  .guide-card strong {
    font-size: 13.5px;
  }

  .guide-card p {
    font-size: 12px;
    line-height: 1.6;
  }

  .guide-icon {
    width: 26px;
    height: 26px;
    font-size: 12px;
  }

  .hint-list {
    padding-left: 16px;
    font-size: 13px;
    line-height: 1.7;
  }
}
</style>
