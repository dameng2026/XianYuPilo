<template>
  <section class="not-found-page" aria-labelledby="not-found-title">
    <EmptyState
      variant="error"
      icon="404"
      title="页面不存在"
      :description="description"
    >
      <template #actions>
        <AppButton type="primary" @click="emit('navigate', 'dashboard')">返回导航面板</AppButton>
        <AppButton @click="emit('navigate', 'settings-about')">查看使用说明</AppButton>
      </template>
    </EmptyState>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import AppButton from '../components/AppButton.vue'
import EmptyState from '../components/EmptyState.vue'

const props = defineProps({ requestedRoute: { type: String, default: '' } })
const emit = defineEmits(['navigate'])
const description = computed(() => props.requestedRoute
  ? `未找到“${props.requestedRoute}”对应的页面。链接可能已失效或功能已下线。`
  : '当前链接可能已失效或功能已下线。')
</script>

<style scoped>
.not-found-page {
  max-width: 760px;
  margin: 36px auto;
}

.not-found-page :deep(.empty-cta-icon) {
  width: 72px;
  font-size: 17px;
}
</style>
