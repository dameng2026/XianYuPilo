<template>
  <div class="aics-page">
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <div v-if="loading" class="aics-loading">配置加载中...</div>
    <div v-else-if="configAvailable === false" class="aics-unavailable" role="alert">
      <strong>AI 客服配置状态未知</strong>
      <p>持久化配置读取失败。为避免用页面默认值覆盖现有配置，编辑、测试、上传与保存均已禁用。</p>
      <button type="button" class="aics-retry-btn" @click="load">重试读取配置</button>
    </div>
    <div v-else class="aics-grid">
      <div class="aics-main">
        <CardPanel title="AI 客服工作模式" desc="主开关开启且选择自动或混合模式后，系统才会按下方运行策略处理买家消息">
          <div class="aics-form">
            <div class="aics-row aics-row-toggle">
              <div>
                <strong>启用 AI 自动回复</strong>
                <p>是否实际发送还受接待模式、账号/商品范围、工作时段、人工接管、日额度、模型与账号连接状态约束。</p>
              </div>
              <button type="button" :class="['aics-switch', { on: form.enabled }]" :aria-pressed="form.enabled" aria-label="启用 AI 自动回复" @click="form.enabled = !form.enabled">
                <span class="aics-switch-knob" />
              </button>
            </div>

            <div class="aics-row">
              <label>策略时区</label>
              <select v-model="form.timeZone" class="aics-input">
                <option value="Asia/Shanghai">Asia/Shanghai（UTC+08:00）</option>
                <option value="UTC">UTC（UTC+00:00）</option>
              </select>
              <p class="aics-hint">工作时段和每日回复额度都按此时区计算，不使用浏览器本地时区。</p>
            </div>

            <div class="aics-row aics-row-toggle">
              <div>
                <strong>全天时段自动回复</strong>
                <p>开启后配置为全天候处理时段；实际回复仍依赖模型、账号连接和平台服务状态。</p>
              </div>
              <button type="button" :class="['aics-switch', { on: form.workHours24 }]" :aria-pressed="form.workHours24" aria-label="全天时段自动回复" @click="form.workHours24 = !form.workHours24">
                <span class="aics-switch-knob" />
              </button>
            </div>

            <div v-if="!form.workHours24" class="aics-row">
              <label>工作时段</label>
              <div class="aics-time-pair">
                <input v-model="form.workStart" type="time" class="aics-input" />
                <span>至</span>
                <input v-model="form.workEnd" type="time" class="aics-input" />
              </div>
              <p class="aics-hint">开始时间晚于结束时间表示跨午夜，例如 22:00–06:00；结束时刻不包含在工作时段内。</p>
            </div>

            <div class="aics-row">
              <label>接待模式</label>
              <select v-model="form.mode" class="aics-input">
                <option value="auto">自动模式（按安全模式配置执行关键词门禁）</option>
                <option value="hybrid">混合模式（命中人工/黑名单关键词时 AI 停答）</option>
                <option value="manual">人工模式（不调用模型、不自动发送）</option>
              </select>
            </div>

            <div class="aics-row">
              <label>回复延时（秒）</label>
              <input v-model.number="form.replyDelaySeconds" type="number" min="5" max="120" class="aics-input" />
              <p class="aics-hint">建议保持 8 到 15 秒：系统会把这段时间内的连续咨询合并为一次回复。</p>
            </div>

            <div class="aics-row aics-row-toggle">
              <div>
                <strong>携带对话上下文</strong>
                <p>开启后 AI 会读取最近 10 条历史消息以理解语境。</p>
              </div>
              <button type="button" :class="['aics-switch', { on: form.carryContext }]" :aria-pressed="form.carryContext" aria-label="携带对话上下文" @click="form.carryContext = !form.carryContext">
                <span class="aics-switch-knob" />
              </button>
            </div>

            <div class="aics-row aics-row-toggle">
              <div>
                <strong>人工干预自动暂停</strong>
                <p>同一账号、同一会话检测到近期非 AI 客服的卖家端消息后暂停；来源无法确认的卖家消息按人工接管处理。</p>
              </div>
              <button type="button" :class="['aics-switch', { on: form.pauseOnHumanIntervene }]" :aria-pressed="form.pauseOnHumanIntervene" aria-label="人工干预自动暂停" @click="form.pauseOnHumanIntervene = !form.pauseOnHumanIntervene">
                <span class="aics-switch-knob" />
              </button>
            </div>

            <div v-if="form.pauseOnHumanIntervene" class="aics-row">
              <label>人工接管暂停时长（分钟）</label>
              <input v-model.number="form.humanInterventionPauseMinutes" type="number" min="1" max="1440" class="aics-input" />
              <p class="aics-hint">窗口结束后，新的买家消息才重新具备自动回复资格。</p>
            </div>
          </div>
        </CardPanel>

        <CardPanel title="客服角色与人设" desc="AI 客服的身份设定、欢迎语与知识库" style="margin-top:16px">
          <div class="aics-form">
            <div class="aics-row">
              <label>客服人设</label>
              <input v-model="form.persona" class="aics-input" placeholder="如：专业客服" />
            </div>

            <div class="aics-row">
              <label>回复语气</label>
              <select v-model="form.tone" class="aics-input">
                <option value="friendly">友好亲切</option>
                <option value="professional">专业严谨</option>
                <option value="casual">轻松活泼</option>
              </select>
            </div>

            <div class="aics-row">
              <label>回复语言</label>
              <select v-model="form.language" class="aics-input">
                <option value="zh-CN">简体中文</option>
                <option value="en">English</option>
              </select>
            </div>

            <div class="aics-row">
              <div class="aics-label-row">
                <label>系统提示词（System Prompt）</label>
                <button type="button" class="aics-restore-btn" @click="restoreDefault('systemPrompt')">恢复默认</button>
              </div>
              <textarea
                v-model="form.systemPrompt"
                class="aics-input aics-textarea"
                rows="5"
                placeholder="定义 AI 的角色、店铺信息、商品特色与回复边界"
              ></textarea>
            </div>

            <div class="aics-row">
              <div class="aics-label-row">
                <label>知识库（优先于默认配置）</label>
                <span class="aics-kb-count">共 {{ form.knowledgeBases.length }} 份</span>
              </div>
              <div class="aics-upload-area">
                <input
                  ref="kbFileInputRef"
                  type="file"
                  accept=".md,.txt,.pptx,.xlsx,.csv"
                  style="display:none"
                  @change="onKbFileChange"
                />
                <button type="button" class="aics-upload-btn" :disabled="kbUploading" @click="kbFileInputRef?.click()">
                  {{ kbUploading ? '正在提取...' : '上传知识库文件' }}
                </button>
                <button type="button" class="aics-upload-btn" @click="addKnowledgeBase">新增手动知识库</button>
                <span class="aics-upload-hint">支持多份内容叠加，AI 会优先读取自定义知识库。</span>
              </div>
              <div class="aics-entry-list">
                <div v-for="(item, index) in form.knowledgeBases" :key="`kb-${index}`" class="aics-entry-card">
                  <div class="aics-entry-head">
                    <input v-model="item.name" class="aics-input" placeholder="知识库名称" />
                    <button type="button" class="aics-entry-remove" @click="removeKnowledgeBase(index)">删除</button>
                  </div>
                  <textarea
                    v-model="item.content"
                    class="aics-input aics-textarea aics-kb-textarea"
                    rows="6"
                    placeholder="填写商品参数、发货说明、售后口径、店铺边界等"
                  ></textarea>
                  <div class="aics-entry-meta">
                    <span>{{ item.source === 'upload' ? '来自文件' : '手动维护' }}</span>
                    <span>{{ (item.content || '').length }} 字</span>
                  </div>
                </div>
                <div v-if="!form.knowledgeBases.length" class="aics-empty-tip">还没有添加自定义知识库，当前将使用系统默认知识库。</div>
              </div>
            </div>

            <div class="aics-row">
              <div class="aics-label-row">
                <label>聊天规则（优先于默认规则）</label>
                <span class="aics-kb-count">共 {{ form.chatRules.length }} 条</span>
              </div>
              <div class="aics-entry-list">
                <div v-for="(item, index) in form.chatRules" :key="`rule-${index}`" class="aics-entry-card">
                  <div class="aics-entry-head">
                    <input v-model="item.name" class="aics-input" placeholder="规则名称" />
                    <button type="button" class="aics-entry-remove" @click="removeChatRule(index)">删除</button>
                  </div>
                  <textarea
                    v-model="item.content"
                    class="aics-input aics-textarea"
                    rows="4"
                    placeholder="例如：只能回答商品本身，不要主动延展售后承诺"
                  ></textarea>
                </div>
                <div v-if="!form.chatRules.length" class="aics-empty-tip">暂未添加自定义聊天规则，当前将使用默认规则。</div>
              </div>
              <button type="button" class="aics-upload-btn" @click="addChatRule">新增聊天规则</button>
            </div>
          </div>
        </CardPanel>

        <CardPanel title="安全与会话策略" desc="命中明确配置的关键词时停止 AI 回复，把会话留给人工处理" style="margin-top:16px">
          <div class="aics-form">
            <div class="aics-row aics-row-toggle">
              <div>
                <strong>自动模式启用关键词门禁</strong>
                <p>自动模式下命中下方任一关键词时 AI 停答；混合模式始终执行该门禁。</p>
              </div>
              <button
                type="button"
                :class="['aics-switch', { on: keywordGateEnabled }]"
                :disabled="form.mode === 'hybrid'"
                :aria-pressed="keywordGateEnabled"
                aria-label="关键词安全门禁"
                @click="form.safeMode = !form.safeMode"
              >
                <span class="aics-switch-knob" />
              </button>
            </div>

            <div class="aics-row">
              <label>转人工关键词</label>
              <input v-model="form.handoffKeywords" class="aics-input" placeholder="用 、 分隔，如：退款、投诉、维权" />
              <p class="aics-hint">命中后系统不调用模型、不发送 AI 回复；不会自动创建人工工单。</p>
            </div>

            <div class="aics-row">
              <label>会话黑名单关键词</label>
              <input v-model="form.blacklistKeywords" class="aics-input" placeholder="命中后 AI 不回复，如：低价、加微" />
            </div>

            <div class="aics-row">
              <label>每日最大回复数</label>
              <input v-model.number="form.maxDailyReplies" type="number" min="1" max="10000" class="aics-input" />
              <p class="aics-hint">每个账号按策略时区的自然日独立计数。生成失败或平台明确未接收会释放名额；已发送和发送结果未知会保守计入，达到上限后不调用模型也不发送。</p>
            </div>
          </div>
        </CardPanel>

        <div class="aics-actions">
          <button type="button" class="aics-save-btn" :disabled="saving" @click="save">{{ saving ? '保存中...' : '保存配置' }}</button>
          <button type="button" class="aics-test-btn" :disabled="testing" @click="openTestPanel">{{ testing ? '测试中...' : '测试 AI 回复' }}</button>
        </div>
      </div>

      <aside class="aics-side">
        <CardPanel title="模型测试预览">
          <div class="aics-preview">
            <div class="aics-bubble them">这个价格还能再优惠吗？</div>
            <div v-if="testReply" class="aics-bubble me">{{ testReply }}</div>
            <div v-else class="aics-bubble me">点击下方“生成回复”按钮查看当前模型返回效果。</div>
          </div>

          <div class="aics-test-form">
            <textarea v-model="testMessage" class="aics-input" rows="2" placeholder="输入模拟买家消息..."></textarea>
            <button type="button" class="aics-test-btn" :disabled="testing || !testMessage.trim()" @click="runTest">
              {{ testing ? '生成中...' : '生成回复' }}
            </button>
          </div>

          <div v-if="testError" class="aics-error-box">
            <p class="aics-error">{{ testError }}</p>
            <button type="button" class="aics-retry-btn" :disabled="testing" @click="runTest">{{ testing ? '重试中...' : '重试' }}</button>
          </div>

          <div v-if="testConfigured === false" class="aics-warn-box">
            <p class="aics-warn">AI 模型未配置，请先到「系统设置 / 模型配置」填写 baseUrl、apiKey 与模型名称。</p>
            <button type="button" class="aics-retry-btn" @click="goToModelConfig">前往模型配置</button>
          </div>
        </CardPanel>

        <CardPanel title="AI 客服状态" style="margin-top:16px">
          <div class="aics-status-list">
            <div class="aics-status-row">
              <span>当前状态</span>
              <b :class="form.enabled && form.mode !== 'manual' ? 'green' : 'red'">{{ configuredStatusText }}</b>
            </div>
            <div class="aics-status-row">
              <span>工作时段</span>
              <b>{{ form.workHours24 ? `全天（${form.timeZone}）` : `${form.workStart}-${form.workEnd}（${form.timeZone}）` }}</b>
            </div>
            <div class="aics-status-row">
              <span>接待模式</span>
              <b>{{ modeText }}</b>
            </div>
            <div class="aics-status-row">
              <span>安全模式</span>
              <b :class="keywordGateEnabled ? 'green' : 'red'">{{ keywordGateEnabled ? '关键词门禁开启' : '关键词门禁关闭' }}</b>
            </div>
            <div class="aics-status-row">
              <span>自定义知识库</span>
              <b>{{ form.knowledgeBases.length }} 份</b>
            </div>
            <div class="aics-status-row">
              <span>自定义规则</span>
              <b>{{ form.chatRules.length }} 条</b>
            </div>
          </div>
        </CardPanel>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import CardPanel from '../../components/CardPanel.vue'
import {
  getAiCsDefaults,
  getBusinessSettings,
  saveBusinessSettings,
  testAiCustomerService,
  uploadKnowledgeBase
} from '../../api/businessSettings.js'
import { confirmAction } from '../../utils/confirmAction.js'

const emit = defineEmits(['navigate'])

const loading = ref(true)
const configAvailable = ref(null)
const saving = ref(false)
const testing = ref(false)
const success = ref('')
const error = ref('')

const testMessage = ref('你好，这个商品还能再优惠点吗？')
const testReply = ref('')
const testError = ref('')
const testConfigured = ref(null)

const kbFileInputRef = ref(null)
const kbUploading = ref(false)

const form = reactive({
  enabled: false,
  mode: 'hybrid',
  workHours24: true,
  workStart: '09:00',
  workEnd: '22:00',
  timeZone: 'Asia/Shanghai',
  persona: '专业客服',
  tone: 'friendly',
  language: 'zh-CN',
  replyDelaySeconds: 8,
  carryContext: true,
  pauseOnHumanIntervene: true,
  humanInterventionPauseMinutes: 30,
  systemPrompt: '',
  knowledgeBase: '',
  knowledgeBases: [],
  defaultKnowledgeBases: [],
  chatRules: [],
  defaultChatRules: [],
  blacklistKeywords: '',
  maxDailyReplies: 200,
  safeMode: true,
  handoffKeywords: '退款、投诉、赔付、维权、改地址'
})

const LEGACY_SYSTEM_PROMPT_MARKERS = [
  '你是闲鱼店铺的专业客服助手',
  '你是本店的AI客服',
  '使用“您好”“亲”等称呼'
]

const modeText = computed(() => ({
  auto: '自动模式',
  hybrid: '混合模式',
  manual: '人工模式'
}[form.mode] || '-'))

const configuredStatusText = computed(() => {
  if (!form.enabled) return '主开关已停用'
  if (form.mode === 'manual') return '人工模式（不外发）'
  return '自动策略已配置'
})

const keywordGateEnabled = computed(() => form.mode === 'hybrid' || form.safeMode)

function resetNotices() {
  success.value = ''
  error.value = ''
}

function setSuccess(message) {
  success.value = message
  error.value = ''
}

function setError(message) {
  error.value = message
  success.value = ''
}

function normalizeEntry(item, fallbackName) {
  if (!item) return null
  if (typeof item === 'string') {
    const content = item.trim()
    if (!content) return null
    return { name: fallbackName, content, source: 'manual' }
  }
  const content = String(item.content || '').trim()
  if (!content) return null
  return {
    name: String(item.name || item.title || fallbackName),
    content,
    source: String(item.source || 'manual')
  }
}

function normalizeEntries(raw, fallbackText = '', prefix = '内容') {
  const list = Array.isArray(raw)
    ? raw.map((item, index) => normalizeEntry(item, `${prefix}${index + 1}`)).filter(Boolean)
    : []
  if (!list.length && String(fallbackText || '').trim()) {
    list.push({ name: `${prefix}1`, content: String(fallbackText).trim(), source: 'manual' })
  }
  return list
}

function looksLikeLegacyText(value, markers) {
  const text = String(value || '').trim()
  return text && markers.some(marker => text.includes(marker))
}

async function load() {
  loading.value = true
  configAvailable.value = null
  resetNotices()
  try {
    const [configResult, defaultsResult] = await Promise.allSettled([
      getBusinessSettings('ai-customer-service'),
      getAiCsDefaults()
    ])
    if (configResult.status !== 'fulfilled') {
      configAvailable.value = false
      setError(configResult.reason?.message || 'AI 客服持久化配置读取失败')
      return
    }
    const configRes = configResult.value
    const defaultsRes = defaultsResult.status === 'fulfilled' ? defaultsResult.value : {}
    const data = configRes?.data ?? configRes ?? {}
    const defaults = defaultsRes?.data ?? defaultsRes ?? {}

    Object.keys(form).forEach(key => {
      if (data[key] !== undefined) {
        form[key] = data[key]
      } else if (defaults[key] !== undefined) {
        form[key] = defaults[key]
      }
    })

    if (looksLikeLegacyText(form.systemPrompt, LEGACY_SYSTEM_PROMPT_MARKERS) && defaults.systemPrompt) {
      form.systemPrompt = defaults.systemPrompt
    }
    form.knowledgeBases = normalizeEntries(data.knowledgeBases, data.knowledgeBase, '知识库')
    form.defaultKnowledgeBases = normalizeEntries(data.defaultKnowledgeBases, '', '默认知识库')
    form.chatRules = normalizeEntries(data.chatRules, '', '规则')
    form.defaultChatRules = normalizeEntries(data.defaultChatRules, '', '默认规则')
    configAvailable.value = true
  } catch (requestError) {
    if (import.meta.env.DEV) console.error('[AiCs] 加载失败')
    configAvailable.value = false
    setError(requestError?.message || 'AI 客服配置加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  resetNotices()
  if (configAvailable.value !== true) {
    setError('配置状态未知，无法保存；请先重试读取配置')
    return
  }
  const policyError = validatePolicyForm()
  if (policyError) {
    setError(policyError)
    return
  }
  saving.value = true
  try {
    const payload = {
      ...form,
      knowledgeBases: form.knowledgeBases.filter(item => item?.content?.trim()),
      chatRules: form.chatRules.filter(item => item?.content?.trim()),
      knowledgeBase: form.knowledgeBases
        .map(item => item?.content?.trim())
        .filter(Boolean)
        .join('\n\n')
    }
    await saveBusinessSettings('ai-customer-service', payload)
    setSuccess('AI 客服配置已保存')
  } catch (requestError) {
    setError(requestError?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function validatePolicyForm() {
  if (!['Asia/Shanghai', 'UTC'].includes(form.timeZone)) {
    return '请选择页面提供的策略时区'
  }
  const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/
  if (!timePattern.test(String(form.workStart || '')) || !timePattern.test(String(form.workEnd || ''))) {
    return '工作时段必须使用 HH:MM 格式'
  }
  if (!form.workHours24 && form.workStart === form.workEnd) {
    return '非全天工作时段的开始与结束时间不能相同'
  }
  const maxDailyReplies = Number(form.maxDailyReplies)
  if (!Number.isInteger(maxDailyReplies) || maxDailyReplies < 1 || maxDailyReplies > 10000) {
    return '每日最大回复数必须是 1 到 10000 之间的整数'
  }
  const pauseMinutes = Number(form.humanInterventionPauseMinutes)
  if (!Number.isInteger(pauseMinutes) || pauseMinutes < 1 || pauseMinutes > 1440) {
    return '人工接管暂停时长必须是 1 到 1440 之间的整数'
  }
  return ''
}

function openTestPanel() {
  // A previous successful test used to make this button a no-op. Always run a
  // fresh request so operators can validate a newly saved model configuration.
  if (configAvailable.value !== true) {
    setError('配置状态未知，无法测试；请先重试读取配置')
    return
  }
  runTest()
}

async function runTest() {
  if (configAvailable.value !== true) {
    setError('配置状态未知，无法测试；请先重试读取配置')
    return
  }
  if (!testMessage.value.trim()) return

  testing.value = true
  testReply.value = ''
  testError.value = ''
  testConfigured.value = null
  resetNotices()

  try {
    const res = await testAiCustomerService(testMessage.value.trim())
    const data = res?.data ?? res ?? {}
    if (data?.ok) {
      testReply.value = data.reply || '（无回复内容）'
      return
    }

    if (data?.errorCode === 'NOT_CONFIGURED' || data?.configured === false) {
      testConfigured.value = false
      return
    }

    if (data?.errorCode === 'AI_ERROR') {
      testError.value = data?.reply || data?.message || 'AI 调用失败，请稍后重试'
      return
    }

    testError.value = data?.reply || data?.message || 'AI 未返回有效回复'
  } catch (requestError) {
    const message = requestError?.message || '网络异常，请检查网络连接后重试'
    if (Number(requestError?.status) === 503 && message.includes('未配置')) {
      testConfigured.value = false
    } else {
      testError.value = message
    }
  } finally {
    testing.value = false
  }
}

async function onKbFileChange(event) {
  if (configAvailable.value !== true) {
    setError('配置状态未知，无法上传；请先重试读取配置')
    return
  }
  const file = event.target.files?.[0]
  if (!file) return
  event.target.value = ''

  if (file.size > 10 * 1024 * 1024) {
    setError('文件不能超过 10MB')
    return
  }

  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!['.md', '.txt', '.pptx', '.xlsx', '.csv'].includes(ext)) {
    setError('仅支持 .md / .txt / .pptx / .xlsx / .csv；旧版 .ppt / .xls 请先另存为新版格式')
    return
  }

  kbUploading.value = true
  resetNotices()
  try {
    const res = await uploadKnowledgeBase(file)
    const data = res?.data ?? res ?? {}
    const extractedText = data?.extractedText || ''
    const ruleCount = data?.ruleCount || 0
    const fileName = data?.fileName || file.name
    if (!extractedText) {
      setError('未能从文件中提取有效内容')
      return
    }
    form.knowledgeBases.push({
      name: fileName,
      content: extractedText,
      source: 'upload'
    })
    setSuccess(`已从 ${fileName} 提取 ${ruleCount} 条内容，并加入知识库`)
  } catch (requestError) {
    setError(requestError?.message || '文件上传失败')
  } finally {
    kbUploading.value = false
  }
}

function addKnowledgeBase() {
  form.knowledgeBases.push({ name: `知识库${form.knowledgeBases.length + 1}`, content: '', source: 'manual' })
}

function removeKnowledgeBase(index) {
  form.knowledgeBases.splice(index, 1)
}

function addChatRule() {
  form.chatRules.push({ name: `规则${form.chatRules.length + 1}`, content: '', source: 'manual' })
}

function removeChatRule(index) {
  form.chatRules.splice(index, 1)
}

async function restoreDefault(field) {
  if (configAvailable.value !== true) {
    setError('配置状态未知，无法恢复默认值；请先重试读取配置')
    return
  }
  if (field !== 'systemPrompt') return
  const label = '系统提示词'
  const confirmed = await confirmAction({
    title: `恢复默认${label}？`,
    description: `恢复默认将覆盖当前${label}内容，是否继续？`,
    confirmText: '恢复默认'
  })
  if (!confirmed) return

  resetNotices()
  try {
    const res = await getAiCsDefaults()
    const data = res?.data ?? res ?? {}
    if (data[field] !== undefined) {
      form[field] = data[field]
      setSuccess(`已恢复默认${label}，请记得保存配置`)
    }
  } catch (requestError) {
    setError(requestError?.message || `恢复默认${label}失败`)
  }
}

function goToModelConfig() {
  emit('navigate', 'settings-model')
}

function onHeaderAction(event) {
  if (event.detail === 'aics-save') save()
  if (event.detail === 'aics-test') openTestPanel()
  if (event.detail === 'aics-reload') load()
}

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-header-action', onHeaderAction)
})
</script>

<style scoped>
.aics-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.aics-loading {
  padding: 40px;
  text-align: center;
  color: #6b7a90;
}

.aics-unavailable {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 24px;
  border: 1px solid #fecaca;
  border-radius: 14px;
  background: #fff7f7;
  color: #991b1b;
}

.aics-unavailable p {
  margin: 0;
  color: #7f1d1d;
  font-size: 13px;
  line-height: 1.6;
}

.aics-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 16px;
  align-items: start;
}

.aics-main,
.aics-side {
  display: flex;
  flex-direction: column;
}

.aics-form {
  display: grid;
  gap: 16px;
  padding: 4px 2px;
}

.aics-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.aics-row > label {
  font-size: 12px;
  color: #6b7a90;
  font-weight: 600;
}

.aics-row-toggle {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.aics-row-toggle > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.aics-row-toggle strong {
  font-size: 14px;
  color: #12233f;
}

.aics-row-toggle p {
  font-size: 12px;
  color: #6b7a90;
  margin: 0;
}

.aics-input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border: 1px solid #dbe6f6;
  border-radius: 12px;
  background: #fff;
  font-size: 13px;
  color: #172b4d;
  outline: 0;
  transition: border-color .2s;
}

.aics-input:focus {
  border-color: #2563eb;
}

.aics-textarea {
  height: auto;
  min-height: 80px;
  padding: 10px 12px;
  resize: vertical;
  line-height: 1.6;
}

.aics-time-pair {
  display: flex;
  gap: 8px;
  align-items: center;
}

.aics-time-pair .aics-input {
  flex: 1;
}

.aics-hint {
  margin: 2px 0 0;
  font-size: 11px;
  color: #99a4b4;
}

.aics-switch {
  width: 44px;
  height: 24px;
  border-radius: 999px;
  border: 0;
  background: #cbd5e1;
  cursor: pointer;
  position: relative;
  transition: background .2s;
  flex-shrink: 0;
  padding: 0;
}

.aics-switch.on {
  background: #22c55e;
}

.aics-switch:disabled {
  cursor: not-allowed;
  opacity: .75;
}

.aics-switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .2);
  transition: left .2s;
}

.aics-switch.on .aics-switch-knob {
  left: 22px;
}

.aics-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.aics-save-btn,
.aics-test-btn {
  padding: 10px 20px;
  border-radius: 12px;
  border: 0;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  transition: all .2s;
}

.aics-save-btn {
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: #fff;
  box-shadow: 0 8px 20px rgba(37, 99, 235, .22);
}

.aics-save-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.aics-save-btn:disabled,
.aics-test-btn:disabled,
.aics-upload-btn:disabled,
.aics-retry-btn:disabled {
  opacity: .6;
  cursor: not-allowed;
}

.aics-test-btn {
  background: #fff;
  color: #2563eb;
  border: 1px solid #bfdbfe;
}

.aics-test-btn:hover:not(:disabled),
.aics-upload-btn:hover:not(:disabled),
.aics-retry-btn:hover:not(:disabled) {
  background: #eff6ff;
}

.aics-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0 12px;
}

.aics-bubble {
  max-width: 90%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.6;
}

.aics-bubble.them {
  align-self: flex-start;
  background: #f6f9ff;
  color: #31445f;
  border-radius: 14px 14px 14px 4px;
}

.aics-bubble.me {
  align-self: flex-end;
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: #fff;
  border-radius: 14px 14px 4px 14px;
}

.aics-test-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.aics-test-form textarea {
  width: 100%;
}

.aics-status-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0;
}

.aics-status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.aics-status-row span {
  color: #6b7a90;
}

.aics-status-row b {
  color: #12233f;
}

.aics-status-row b.green {
  color: #16a34a;
}

.aics-status-row b.red {
  color: #ef4444;
}

.aics-kb-textarea {
  min-height: 160px;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
}

.aics-kb-count {
  font-size: 11px;
  color: #99a4b4;
}

.aics-upload-area {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  padding: 10px;
  border: 1px dashed #dbe6f6;
  border-radius: 10px;
  background: #fafbfc;
  flex-wrap: wrap;
}

.aics-upload-btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid #bfdbfe;
  background: #fff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all .2s;
}

.aics-upload-hint {
  font-size: 11px;
  color: #99a4b4;
}

.aics-entry-list {
  display: grid;
  gap: 12px;
  margin-top: 10px;
}

.aics-entry-card {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #e5edf8;
  border-radius: 10px;
  background: #fbfdff;
}

.aics-entry-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.aics-entry-remove {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid #fecaca;
  background: #fff;
  color: #ef4444;
  font-size: 12px;
  cursor: pointer;
}

.aics-entry-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 11px;
  color: #99a4b4;
}

.aics-empty-tip {
  padding: 10px 0 2px;
  font-size: 12px;
  color: #94a3b8;
}

.aics-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.aics-restore-btn {
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #6b7a90;
  font-size: 11px;
  cursor: pointer;
  transition: all .2s;
}

.aics-restore-btn:hover {
  color: #2563eb;
  border-color: #bfdbfe;
}

.aics-error-box,
.aics-warn-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  padding: 10px;
  border-radius: 8px;
}

.aics-error-box {
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.aics-warn-box {
  background: #fffbeb;
  border: 1px solid #fde68a;
}

.aics-error {
  margin: 0;
  color: #ef4444;
  font-size: 12px;
}

.aics-warn {
  margin: 0;
  color: #b45309;
  font-size: 12px;
  line-height: 1.6;
}

.aics-retry-btn {
  align-self: flex-start;
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #dbe6f6;
  background: #fff;
  color: #2563eb;
  font-size: 12px;
  cursor: pointer;
}

@media (max-width: 1200px) {
  .aics-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .aics-page {
    gap: 12px;
  }

  .aics-actions {
    flex-wrap: wrap;
    gap: 10px;
  }
}
</style>
