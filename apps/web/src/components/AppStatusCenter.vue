<template>
  <div class="app-status-center" aria-atomic="true">
    <section v-if="loading" class="app-status-banner loading" role="status" aria-live="polite">
      <span class="app-status-spinner" aria-hidden="true"></span>
      <div class="app-status-message">正在同步数据...</div>
    </section>

    <section v-if="!online" class="app-status-banner offline" role="alert" aria-live="assertive">
      <span class="app-status-dot" aria-hidden="true"></span>
      <div>
        <strong>当前网络已断开</strong>
        <p>无法提交或刷新数据；网络恢复后页面会自动继续连接。</p>
      </div>
    </section>

    <section
      v-if="notice"
      class="app-status-banner notice"
      :class="notice.type || 'info'"
      :role="isUrgent ? 'alert' : 'status'"
      :aria-live="isUrgent ? 'assertive' : 'polite'"
    >
      <div class="app-status-message">{{ notice.text }}</div>
      <button
        v-if="notice.retry"
        type="button"
        class="app-status-retry"
        :disabled="retrying || !online"
        :aria-busy="retrying"
        @click="emit('retry')"
      >
        {{ retrying ? '重试中...' : '重试' }}
      </button>
      <button type="button" class="app-status-close" aria-label="关闭提示" @click="emit('dismiss')">×</button>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  online: { type: Boolean, default: true },
  notice: { type: Object, default: null },
  loading: Boolean,
  retrying: Boolean,
})
const emit = defineEmits(['dismiss', 'retry'])
const isUrgent = computed(() => ['error', 'warn'].includes(props.notice?.type))
</script>

<style scoped>
.app-status-center {
  position: fixed;
  top: max(14px, env(safe-area-inset-top));
  left: 50%;
  z-index: 2200;
  width: min(560px, calc(100vw - 32px));
  transform: translateX(-50%);
  display: grid;
  gap: 10px;
  pointer-events: none;
}

.app-status-banner {
  min-height: 52px;
  padding: 12px 14px;
  border: 1px solid #d8e5fa;
  border-radius: 14px;
  background: rgba(255, 255, 255, .97);
  box-shadow: 0 18px 48px rgba(25, 48, 86, .2);
  color: #24466f;
  display: flex;
  align-items: center;
  gap: 12px;
  pointer-events: auto;
  backdrop-filter: blur(12px);
}

.app-status-banner.offline,
.app-status-banner.warn {
  border-color: #f2ca73;
  background: rgba(255, 249, 232, .98);
  color: #8a5300;
}

.app-status-banner.error {
  border-color: #ffc9c9;
  background: rgba(255, 245, 245, .98);
  color: #c73535;
}

.app-status-banner.success {
  border-color: #a9e5c4;
  background: rgba(241, 253, 246, .98);
  color: #137547;
}

.app-status-banner.loading {
  min-height: 42px;
  padding-block: 9px;
}

.app-status-spinner {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  border: 2px solid rgba(47, 107, 255, .28);
  border-top-color: #2f6bff;
  border-radius: 50%;
  animation: app-status-spin .8s linear infinite;
}

.app-status-retry {
  min-width: 64px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid currentColor;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  font-weight: 800;
}

.app-status-retry:disabled {
  cursor: not-allowed;
  opacity: .55;
}

@keyframes app-status-spin {
  to { transform: rotate(360deg); }
}

.app-status-dot {
  width: 10px;
  height: 10px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #e48a00;
  box-shadow: 0 0 0 5px rgba(228, 138, 0, .13);
}

.app-status-banner strong,
.app-status-banner p {
  margin: 0;
}

.app-status-banner p {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  font-weight: 500;
}

.app-status-message {
  min-width: 0;
  flex: 1;
  line-height: 1.5;
  font-weight: 700;
}

.app-status-close {
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  font-size: 24px;
  line-height: 1;
}

.app-status-close:hover {
  background: rgba(20, 55, 105, .08);
}

@media (max-width: 600px) {
  .app-status-center {
    top: max(8px, env(safe-area-inset-top));
    width: calc(100vw - 20px);
  }
}
</style>
