<template>
  <div class="amap-settings-page">
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <section class="page-hero">
      <div class="page-hero-copy">
        <span class="page-pill">Map Settings</span>
        <h1>高德地图</h1>
        <p>高德地图 API Key 已从系统总览中拆出，单独维护更适合做授权轮换、接口联调与问题排查。</p>

        <div class="page-actions">
          <AppButton type="primary" :loading="saving" :disabled="!configAvailable" @click="save">保存配置</AppButton>
          <AppButton :loading="loading" @click="loadPage">重新加载</AppButton>
        </div>
      </div>

      <div class="page-status">
        <div class="status-card" :class="runtimeStatusAvailable && runtimeStatus.amapConfigured ? 'green' : 'orange'">
          <span>地图状态</span>
          <strong>{{ runtimeStatusAvailable ? (runtimeStatus.amapConfigured ? '已配置' : '未配置') : '状态未知' }}</strong>
          <small>发布商品的地址搜索和 POI 选择都会实时读取这里的 Key。</small>
        </div>
      </div>
    </section>

    <div class="page-grid">
      <CardPanel title="高德地图 API Key" desc="把 Key 填在这里，保存后前台发布商品与工作流地址搜索会立即使用最新配置。">
        <div class="config-overview">
          <article class="overview-card">
            <span>推荐顺序</span>
            <strong>申请 Key → 选择 Web 服务 → 保存后立即验证</strong>
            <p>先拿到服务端可用的 Web 服务 Key，再回到此页粘贴保存，避免拿错前端专用类型。</p>
          </article>
          <article class="overview-card">
            <span>影响范围</span>
            <strong>商品发布、工作流地址选择、POI 搜索</strong>
            <p>只要页面里有地图联想与地址选择能力，都会走这里的统一配置，不需要重复填写。</p>
          </article>
        </div>

        <div class="field-grid">
          <AdminConfigField
            label="AMap API Key"
            hint="直接粘贴高德控制台生成的 Key，保存后系统会自动切换到新的地图授权。"
            meta="不会在页面回显完整 Key；如需轮换，直接覆盖保存即可，无需重启服务。"
            badge="地址服务"
            required
          >
            <SecretInput
              v-model="form.amapApiKey"
              :placeholder="config.amapApiKeyConfigured ? '已保存，直接输入新值可覆盖' : '请输入高德地图 API Key'"
              autocomplete="off"
            />
          </AdminConfigField>
        </div>

        <div class="quick-links">
          <div class="quick-link">
            <strong>申请平台</strong>
            <span>https://lbs.amap.com</span>
          </div>
          <div class="quick-link">
            <strong>服务类型</strong>
            <span>创建 Key 时请选择「Web 服务」</span>
          </div>
          <div class="quick-link">
            <strong>调试接口</strong>
            <span>/api/amap/inputtips</span>
          </div>
        </div>
      </CardPanel>

      <CardPanel title="使用说明" desc="如果你是第一次配置地图服务，先看下面的 3 条速览，再按步骤完成申请与自检。">
        <div class="guide-grid">
          <article class="guide-card">
            <div class="guide-icon">1</div>
            <div>
              <strong>先申请账号</strong>
              <p>访问高德开放平台并完成实名认证，个人与企业账号都可以使用。</p>
            </div>
          </article>
          <article class="guide-card">
            <div class="guide-icon">2</div>
            <div>
              <strong>确认服务平台</strong>
              <p>创建 Key 时请选择 Web 服务，否则服务端 POI 接口会直接鉴权失败。</p>
            </div>
          </article>
          <article class="guide-card">
            <div class="guide-icon">3</div>
            <div>
              <strong>保存后立即验证</strong>
              <p>保存配置并重新加载后，检查状态是否切换为已配置，再去商品发布页测试联想搜索。</p>
            </div>
          </article>
        </div>

        <ol class="hint-list ordered">
          <li><strong>申请高德开放平台账号</strong>：访问 <code>https://lbs.amap.com</code>，注册并完成实名认证（个人或企业均可）。</li>
          <li><strong>创建应用</strong>：进入“控制台 → 应用管理 → 我的应用 → 创建新应用”，应用名可填 <code>xianyu-assistant</code>，类型选“Web端（JS API）”。</li>
          <li><strong>获取 Key</strong>：在应用下“添加 Key”，服务平台必须选 <strong>Web 服务</strong>（用于服务端调用 POI 接口）。复制生成的 Key 粘贴到上方输入框。</li>
          <li><strong>计费说明</strong>：高德地图对个人开发者每日免费提供 5000 次 POI 调用，普通商品发布场景通常远低于配额。</li>
          <li><strong>调试方法</strong>：保存后点击“重新加载”，确认“地图状态”变为“已配置”。若发布商品页仍无法搜索地址，可检查 <code>/api/amap/inputtips</code> 的响应与报错。</li>
          <li><strong>接入位置</strong>：发布商品页的地址搜索会读取这里的配置；当前版本没有“常用地址历史”功能。</li>
        </ol>
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
  amapApiKey: '',
})

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  loadPage()
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-header-action', onHeaderAction)
})

async function loadPage() {
  await loadBundle({ includeRuntimeStatus: true })
  if (configAvailable.value) form.amapApiKey = config.amapApiKey || ''
}

async function save() {
  if (!configAvailable.value) return
  const payload = cloneOpenSourceConfig(config)
  payload.amapApiKey = form.amapApiKey.trim()
  const saved = await saveConfig(payload, { successMessage: '高德地图配置已保存' })
  if (!saved) return
  form.amapApiKey = config.amapApiKey || ''
  await refreshRuntimeStatus()
}

function onHeaderAction(event) {
  if (event.detail === 'settings-save') save()
  if (event.detail === 'settings-reload') loadPage()
}
</script>

<style scoped>
.amap-settings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 16px;
  padding: 22px;
  border-radius: 24px;
  border: 1px solid rgba(231, 237, 247, 0.95);
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.12), transparent 32%),
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

.page-status {
  display: flex;
  align-items: stretch;
}

.status-card {
  width: 100%;
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
  grid-template-columns: minmax(0, 1fr);
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

.quick-links {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.quick-link {
  padding: 14px 16px;
  border-radius: 16px;
  background: #f8fbff;
  border: 1px dashed #d3def1;
}

.quick-link strong {
  display: block;
  color: #13213d;
  font-size: 13px;
}

.quick-link span {
  display: block;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.guide-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
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

.hint-list.ordered {
  padding-left: 22px;
  list-style: decimal;
}

.hint-list.ordered li {
  margin-bottom: 6px;
}

.hint-list.ordered code {
  background: rgba(37, 99, 235, 0.08);
  color: #2c63d4;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 12px;
}

.hint-list.ordered strong {
  color: #13213d;
}

@media (max-width: 1080px) {
  .page-hero,
  .config-overview,
  .guide-grid,
  .quick-links {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .amap-settings-page {
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

  .page-status {
    width: 100%;
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
    line-height: 1.55;
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

  .quick-links {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
    margin-top: 12px;
  }

  .quick-link {
    padding: 12px;
    border-radius: 12px;
  }

  .quick-link strong {
    font-size: 13px;
  }

  .quick-link span {
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.55;
    word-break: break-all;
  }

  .guide-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
    margin-bottom: 12px;
  }

  .page-hero > *,
  .config-overview > *,
  .guide-grid > *,
  .quick-links > * {
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

  .hint-list.ordered {
    padding-left: 18px;
  }

  .hint-list.ordered li {
    margin-bottom: 6px;
  }

  .hint-list.ordered code {
    font-size: 11px;
    word-break: break-all;
  }
}
</style>
