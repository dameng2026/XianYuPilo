<template>
  <header class="page-head" :class="{ compact: !title && !subtitle }">
    <div v-if="title || subtitle">
      <h1 v-if="title">{{ title }}</h1>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.default" class="page-head-actions">
      <slot />
    </div>
  </header>
</template>
<script setup>
defineProps({ title: String, subtitle: String })
</script>
<style scoped>
.page-head.compact {
  height: auto;
  min-height: 42px;
  margin-bottom: 16px;
  justify-content: flex-end;
}

.page-head-actions {
  margin-left: auto;
}
</style>
