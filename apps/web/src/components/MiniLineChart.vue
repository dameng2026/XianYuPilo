<template>
  <div class="chart-wrap">
    <svg :viewBox="`0 0 ${width} ${height}`" class="line-chart">
      <g v-if="hasData" class="grid">
        <line v-for="y in [20,60,100,140,180]" :key="y" x1="20" :y1="y" :x2="width-20" :y2="y" />
      </g>
      <polyline v-if="hasData" :points="areaPoints" fill="rgba(22,112,255,.10)" stroke="none" />
      <polyline v-if="hasData" :points="points" fill="none" stroke="var(--primary)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
      <circle v-for="(p,i) in dotList" :key="i" :cx="p.x" :cy="p.y" r="5" fill="white" stroke="var(--primary)" stroke-width="4" />
      <g v-if="hasData" class="axis"><text v-for="item in labelPoints" :key="item.key" :x="item.x" :y="height-10">{{ item.label }}</text></g>
      <text v-else x="370" y="120" text-anchor="middle" fill="#8a98ad">暂无趋势数据</text>
    </svg>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ values: { type: Array, default: () => [] }, labels: { type: Array, default: () => [] } })
const width = 740, height = 240
const normalizedValues = computed(() => props.values.map(value => Math.max(0, Number(value) || 0)))
const hasData = computed(() => normalizedValues.value.length > 0)
const dotList = computed(() => {
  const values = normalizedValues.value
  if (!values.length) return []
  const max = Math.max(1, ...values)
  const step = values.length === 1 ? 0 : (width - 60) / (values.length - 1)
  return values.map((value, index) => ({
    x: values.length === 1 ? width / 2 : 30 + index * step,
    y: 210 - (value / max) * 180
  }))
})
const points = computed(() => dotList.value.map(p => `${p.x},${p.y}`).join(' '))
const areaPoints = computed(() => {
  if (!dotList.value.length) return ''
  return `${dotList.value[0].x},210 ${points.value} ${dotList.value.at(-1).x},210`
})
const labelPoints = computed(() => dotList.value.map((point, index) => ({
  key: `${props.labels[index] || index}-${index}`,
  label: props.labels[index] || String(index + 1),
  x: point.x
})))
</script>
