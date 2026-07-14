<template>
  <div class="auth-reference-page">
    <div class="auth-reference-canvas">
      <img class="auth-reference-image" :src="background" :alt="alt" draggable="false" />
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  background: { type: String, required: true },
  alt: { type: String, default: 'Auth reference background' }
})
</script>
