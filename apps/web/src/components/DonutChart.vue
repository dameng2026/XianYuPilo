<template>
  <div class="donut-row">
    <div class="donut" :style="style"><strong>{{ center }}</strong><span>{{ label }}</span></div>
    <div class="donut-legend">
      <div v-for="(item,i) in items" :key="item.label"><i :style="{background: colors[i%colors.length]}"></i><span>{{ item.label }}</span><b>{{ item.value }}</b></div>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ center: String, label: String, items: Array })
const colors = ['#1977ff','#18c785','#ffb020','#ff6b6b','#9b5cff','#33cdd2']
const style = computed(() => {
  const values = (props.items || []).map(item => Math.max(0, Number(item?.value) || 0))
  const total = values.reduce((sum, value) => sum + value, 0)
  if (!total) return { background: '#eef2f7' }
  let cursor = 0
  const segments = values.map((value, index) => {
    const start = cursor
    cursor += (value / total) * 100
    return `${colors[index % colors.length]} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`
  })
  return { background: `conic-gradient(${segments.join(', ')})` }
})
</script>
