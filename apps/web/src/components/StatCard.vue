<template>
  <div class="stat-card">
    <div :class="['stat-icon', color || 'blue']"><Icon :name="icon" /></div>
    <div class="stat-info">
      <span>{{ title }}</span>
      <strong>{{ value }}</strong>
      <em :class="trend === 'down' ? 'down' : ''">{{ change }}</em>
    </div>
  </div>
</template>
<script setup>
import Icon from './Icon.vue'
defineProps({ title: String, value: [String, Number], change: String, icon: String, color: String, trend: String })
</script>
