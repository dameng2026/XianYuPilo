<template>
  <button
    v-bind="$attrs"
    type="button"
    role="switch"
    :class="['switch', { on }]"
    :aria-checked="on"
    :aria-label="label || (on ? '已开启' : '已关闭')"
    :disabled="disabled || !isInteractive"
  ></button>
</template>

<script setup>
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  on: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
  interactive: { type: Boolean, default: false },
  label: { type: String, default: '' },
})
const attrs = useAttrs()
const isInteractive = computed(() => props.interactive || typeof attrs.onClick === 'function')
</script>

<style scoped>
.switch {
  border: 0;
  padding: 0;
}
.switch:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.switch:focus-visible {
  outline: 3px solid rgba(37, 99, 235, 0.35);
  outline-offset: 2px;
}
</style>
