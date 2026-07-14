<template>
  <button
    :type="nativeType || 'button'"
    :class="['app-btn', type || 'ghost', { loading }]"
    :disabled="disabled || loading"
    :aria-disabled="disabled || loading"
    :aria-busy="loading"
  >
    <span v-if="loading" class="app-btn-spinner" aria-hidden="true"></span>
    <span>{{ loading ? loadingText : '' }}<slot v-if="!loading" /></span>
  </button>
</template>
<script setup>
defineProps({
  type: String,
  nativeType: { type: String, default: 'button' },
  disabled: Boolean,
  loading: Boolean,
  loadingText: { type: String, default: '处理中...' }
})
</script>
<style scoped>
.app-btn:disabled { cursor: not-allowed; opacity: 0.6; }
.app-btn.loading { position: relative; pointer-events: none; }
.app-btn-spinner { display:inline-block; width:12px; height:12px; border-radius:999px; border:2px solid currentColor; border-right-color:transparent; margin-right:6px; vertical-align:-2px; animation:app-btn-spin .8s linear infinite; }
@keyframes app-btn-spin { to { transform: rotate(360deg); } }
</style>
