<template>
  <div :class="['auth-shell', `auth-shell-${pageKey}`]">
    <header class="auth-topbar">
      <button type="button" class="brand brand-image auth-brand" @click="emit('navigate', 'dashboard')">
        <img src="/xya/brand/brand_002.png" class="brand-logo brand-icon" alt="XianYuAssistant" />
      </button>
      <div class="auth-lang-switch" aria-label="当前语言：简体中文">
        <TrustedSvg class="auth-lang-icon" :markup="authIcons.globe" />
        <span>简体中文</span>
      </div>
    </header>

    <main class="auth-main">
      <section class="auth-showcase">
        <div class="auth-copy">
          <h1>
            <span class="auth-title-lead">{{ titleLead }}</span>
            <span v-if="titleAccent || titleTail" class="auth-title-group">
              <span class="auth-title-accent">{{ titleAccent }}</span>
              <span v-if="titleTail" class="auth-title-tail">{{ titleTail }}</span>
            </span>
          </h1>
          <p>{{ description }}</p>
        </div>

        <div :class="['auth-feature-row', `auth-feature-row--${features.length}`]">
          <div v-for="item in features" :key="item.title" class="auth-feature-card">
            <TrustedSvg class="auth-feature-icon" :markup="item.icon" />
            <div>
              <strong>{{ item.title }}</strong>
              <small>{{ item.desc }}</small>
            </div>
          </div>
        </div>

        <div :class="['auth-visual', visualKind === 'security' ? 'auth-visual-security' : 'auth-visual-dashboard']">
          <img
            v-for="item in visualLayers"
            :key="item.key"
            :class="['auth-visual-layer', item.className]"
            :src="item.src"
            alt=""
          />
          <div v-if="visualKind === 'dashboard'" class="auth-visual-floor-grid"></div>
        </div>

        <div class="auth-stats-card">
          <template v-for="(item, index) in stats" :key="item.value">
            <div class="auth-stat-item">
              <TrustedSvg class="auth-stat-icon" :markup="item.icon" />
              <div>
                <strong>{{ item.value }}</strong>
                <small>{{ item.label }}</small>
              </div>
            </div>
            <div v-if="index < stats.length - 1" class="auth-stat-divider"></div>
          </template>
        </div>
      </section>

      <section class="auth-panel">
        <div class="auth-panel-inner">
          <slot />
        </div>
      </section>
    </main>

    <footer class="auth-footer">
      <span>© {{ resolvedCopyrightYear }} XianYuAssistant 开源项目</span>
      <span>开源软件，请按实际部署主体补充合规信息</span>
      <button type="button" class="footer-link" @click="openDoc('隐私政策')">隐私政策</button>
      <button type="button" class="footer-link" @click="openDoc('用户协议')">用户协议</button>
    </footer>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import TrustedSvg from '../TrustedSvg.vue'
import { authIcons, dashboardVisualLayers, loginFeatures, openLegalDoc, securityVisualLayers, authStats } from './authContent.js'
import { getCopyrightYear } from '../../utils/appMeta.js'

const props = defineProps({
  pageKey: { type: String, required: true },
  titleLead: { type: String, required: true },
  titleAccent: { type: String, default: '' },
  titleTail: { type: String, default: '' },
  description: { type: String, required: true },
  visualKind: { type: String, default: 'dashboard' },
  features: { type: Array, default: null },
  stats: { type: Array, default: null },
  copyrightYear: { type: [String, Number], default: null },
  legalDescription: { type: String, default: '' }
})

const emit = defineEmits(['navigate'])
const resolvedCopyrightYear = computed(() => `${props.copyrightYear ?? getCopyrightYear()}`)

const featureMap = {
  login: loginFeatures
}

const features = computed(() => props.features || featureMap[props.pageKey] || loginFeatures)
const visualLayers = computed(() => (props.visualKind === 'security' ? securityVisualLayers : dashboardVisualLayers))
const stats = computed(() => props.stats || authStats)

function openDoc(title) {
  openLegalDoc(title, props.legalDescription)
}

defineExpose({
  authIcons,
  openDoc
})
</script>
