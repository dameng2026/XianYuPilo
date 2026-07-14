<template>
  <!-- This is the only v-html boundary. `trustedSvg` accepts source-controlled SVG markup and rejects active content. -->
  <!-- eslint-disable-next-line vue/no-v-html -->
  <span class="trusted-svg" aria-hidden="true" v-html="safeMarkup"></span>
</template>

<script setup>
import { computed } from 'vue'
import { trustedSvg } from '../utils/trustedSvg.js'

const props = defineProps({
  markup: { type: String, required: true }
})

const safeMarkup = computed(() => trustedSvg(props.markup))
</script>

<style scoped>
.trusted-svg {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.trusted-svg :deep(svg) {
  display: block;
  max-width: 100%;
  max-height: 100%;
}
</style>
