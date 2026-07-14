<template>
  <div class="empty-cta" :class="variant" role="status">
    <div class="empty-cta-icon" aria-hidden="true">{{ displayIcon }}</div>
    <div>
      <h3>{{ title }}</h3>
      <p v-if="description">{{ description }}</p>
      <div v-if="$slots.actions" class="empty-cta-actions">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  icon: { type: String, default: '' },
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '完成基础配置后，这里会展示对应数据。' },
  variant: { type: String, default: 'default' } // default | search | error | dev
})
const variantIcons = { default: '∅', search: '🔍', error: '⚠', dev: '🚧' }
const displayIcon = computed(() => props.icon || variantIcons[props.variant] || '∅')
</script>

<style scoped>
.empty-cta{display:flex;gap:16px;align-items:flex-start;padding:26px;border:1px dashed #cfd9ea;border-radius:18px;background:linear-gradient(135deg,#fbfdff,#f6f9ff);color:#526079;margin:12px 0}
.empty-cta-icon{width:48px;height:48px;border-radius:16px;background:#edf4ff;color:#0d6bff;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;flex:0 0 auto}
.empty-cta h3{margin:0 0 6px;color:#16213e;font-size:18px}
.empty-cta p{margin:0;line-height:1.7;color:#667085}
.empty-cta-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.empty-cta.search{border-color:#dbe7f5;background:linear-gradient(135deg,#fbfdff,#f0f6ff)}
.empty-cta.search .empty-cta-icon{background:#f0f6ff;color:#3b6fd4}
.empty-cta.error{border-color:#ffd1d1;background:linear-gradient(135deg,#fff8f8,#fff5f5)}
.empty-cta.error .empty-cta-icon{background:#fff0f0;color:#ef4444}
.empty-cta.dev{border-color:#ffe1b0;background:linear-gradient(135deg,#fffaf0,#fff8ea)}
.empty-cta.dev .empty-cta-icon{background:#fff5e6;color:#d97706}
</style>
