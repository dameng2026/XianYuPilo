<template>
  <TrustedSvg class="m-icon" :style="{ width: size + 'px', height: size + 'px' }" :markup="svgContent" />
</template>

<script setup>
import { computed } from 'vue'
import TrustedSvg from '../components/TrustedSvg.vue'
import { Icons } from './MobileIcons.js'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 24 }
})

const svgContent = computed(() => Icons[props.name] || Icons.help)
</script>

<style scoped>
.m-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.m-icon :deep(svg) {
  width: 100%;
  height: 100%;
}
</style>
