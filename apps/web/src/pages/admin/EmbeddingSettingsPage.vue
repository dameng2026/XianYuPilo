<template>
  <div class="embedding-settings-page">
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <section class="page-hero">
      <div class="page-hero-copy">
        <span class="page-pill">Embedding Model</span>
        <h1>向量模型配置</h1>
        <p>向量模型（Embedding）独立维护，用于 RAG 知识库的文档向量化与语义召回。聊天与文本生成请前往“模型配置”页签。</p>

        <div class="page-actions">
          <AppButton type="primary" :loading="saving" :disabled="!configAvailable" @click="save">保存配置</AppButton>
          <AppButton :loading="loading" @click="loadPage">重新加载</AppButton>
        </div>
      </div>

      <div class="hero-badges">
        <div class="status-card" :class="runtimeStatusAvailable && runtimeStatus.embeddingModelConfigured ? 'green' : 'purple'">
          <span>向量模型</span>
          <strong>{{ runtimeStatusAvailable ? (runtimeStatus.embeddingModelConfigured ? '已配置' : '未设置') : '状态未知' }}</strong>
          <small>Embedding / RAG 检索</small>
        </div>
      </div>
    </section>

    <div class="page-grid">
      <CardPanel title="向量模型（Embedding）" desc="RAG 知识库建索引、召回相似内容与检索增强回答，都会优先使用这里的嵌入模型配置。">
        <div class="config-overview">
          <article class="overview-card">
            <span>用途边界</span>
            <strong>只负责“向量化”和“相似度检索”</strong>
            <p>它不负责对话或文案生成，所以这里的模型能力与通用聊天模型完全不同，不建议混填。</p>
          </article>
          <article class="overview-card">
            <span>配置顺序</span>
            <strong>供应商 → 模型名 → Base URL → API Key</strong>
            <p>先保证最基础的可调用链路，再去验证知识库索引、检索和召回质量是否符合预期。</p>
          </article>
        </div>

        <div class="field-grid two">
          <AdminConfigField
            label="模型供应商"
            hint="标记你当前使用的是哪家的向量服务，方便区分 OpenAI、阿里、火山等不同接入。"
            meta="常见示例：openai / dashscope / volcengine。不同供应商的模型名与 Base URL 可能不一致。"
            badge="第一步"
            required
          >
            <input v-model="form.embeddingModel.provider" class="config-input" placeholder="openai / dashscope / volcengine" />
          </AdminConfigField>

          <AdminConfigField
            label="模型名称"
            hint="填写实际用于生成向量的模型名，知识库索引和检索阶段都会直接调用它。"
            meta="常见示例：text-embedding-3-small、text-embedding-v3、doubao-embedding。"
            badge="核心参数"
            required
          >
            <input v-model="form.embeddingModel.modelName" class="config-input" placeholder="text-embedding-3-small" />
          </AdminConfigField>

          <AdminConfigField
            label="接口地址"
            hint="仅支持可解析的公网 HTTPS API 根地址；系统会拒绝明文 HTTP、本机、内网、重定向与代理环境。"
            meta="大多数兼容接口以 /v1 结尾。切换到不同主机时必须同时重新输入 API Key，避免已保存密钥外泄。"
            badge="第二步"
            required
          >
            <input v-model="form.embeddingModel.baseUrl" class="config-input" placeholder="https://api.openai.com/v1" />
          </AdminConfigField>

          <AdminConfigField
            label="API Key"
            hint="保存后不会回显完整 Key；索引构建与检索时会直接使用这项鉴权。"
            meta="修改接口主机时必须重新输入 Key；若导入时报 401/403，请检查 Key 是否过期以及是否属于当前供应商。"
            badge="第三步"
            required
          >
            <SecretInput
              v-model="form.embeddingModel.apiKey"
              :placeholder="config.embeddingModel.apiKeyConfigured ? '已保存，直接输入新值可覆盖' : 'sk-...'"
              autocomplete="off"
            />
          </AdminConfigField>
        </div>
      </CardPanel>

      <CardPanel title="使用说明" desc="先理解向量模型的职责边界，再去调整供应商和模型选型，会少走很多弯路。">
        <div class="guide-grid">
          <article class="guide-card">
            <div class="guide-icon">R</div>
            <div>
              <strong>RAG 优先读取这里</strong>
              <p>知识库导入、切片向量化和检索召回都会优先使用这里的配置，不会自动回退到通用聊天模型。</p>
            </div>
          </article>
          <article class="guide-card">
            <div class="guide-icon">V</div>
            <div>
              <strong>只看向量质量，不看文采</strong>
              <p>向量模型评估重点是检索准确率、相似度语义与速度，而不是回答是否自然流畅。</p>
            </div>
          </article>
          <article class="guide-card">
            <div class="guide-icon">K</div>
            <div>
              <strong>索引失败先查 Key 与地址</strong>
              <p>导入知识库时报错时，最常见原因是 Key 不匹配、Base URL 错填，或模型名不被当前服务支持。</p>
            </div>
          </article>
        </div>

        <ul class="hint-list">
          <li>向量模型仅用于生成文本向量，不能替代通用对话模型；聊天、改写和文案生成请到“模型配置”页签。</li>
          <li>常见供应商包括 OpenAI（text-embedding-3-small/large）、阿里 DashScope（text-embedding-v2/v3）以及火山引擎的 embedding 服务。</li>
          <li>如果这里没有正确配置，RAG 检索往往只能退化为低质量的关键词匹配，召回效果会明显下降。</li>
          <li>Base URL 通常以 <code>/v1</code> 结尾，必须使用公网 HTTPS；当前默认安全策略不允许直接连接本机或内网模型服务。</li>
          <li>API Key 不会完整回显；需要更换时直接覆盖，切换接口主机时也必须重新输入并保存。</li>
        </ul>
      </CardPanel>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive } from 'vue'
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

const form = reactive({
  embeddingModel: {
    provider: '',
    modelName: '',
    baseUrl: '',
    apiKey: '',
  },
})

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  loadPage()
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-header-action', onHeaderAction)
})

function syncForm() {
  Object.assign(form.embeddingModel, config.embeddingModel || {})
}

async function loadPage() {
  await loadBundle({ includeRuntimeStatus: true })
  if (configAvailable.value) syncForm()
}

async function save() {
  if (!configAvailable.value) return
  const payload = cloneOpenSourceConfig(config)
  payload.embeddingModel = {
    provider: form.embeddingModel.provider.trim(),
    modelName: form.embeddingModel.modelName.trim(),
    baseUrl: form.embeddingModel.baseUrl.trim(),
    apiKey: form.embeddingModel.apiKey.trim(),
  }
  const saved = await saveConfig(payload, { successMessage: '向量模型配置已保存' })
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
.embedding-settings-page {
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
    radial-gradient(circle at top left, rgba(39, 123, 255, 0.1), transparent 32%),
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
  background: rgba(13, 107, 255, 0.08);
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

.status-card.purple {
  background: linear-gradient(180deg, rgba(240, 246, 255, 0.98), rgba(255, 255, 255, 0.96));
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

.hint-list code {
  background: rgba(37, 99, 235, 0.08);
  color: #2c63d4;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 12px;
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
  .embedding-settings-page {
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

  .hint-list code {
    font-size: 11px;
    word-break: break-all;
  }
}
</style>
