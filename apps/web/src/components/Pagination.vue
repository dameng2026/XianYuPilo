<template>
  <div v-if="totalPages > 1" class="pagination">
    <span class="page-info">共 {{ total }} 条</span>
    <button class="page-no" type="button" :disabled="current <= 1" aria-label="上一页" @click="go(current - 1)">‹</button>
    <button
      v-for="p in visiblePages"
      :key="p"
      type="button"
      class="page-no"
      :class="{ active: p === current, ellipsis: p === '...' }"
      :disabled="p === '...'"
      @click="typeof p === 'number' && go(p)"
    >
{{ p }}
</button>
    <button class="page-no" type="button" :disabled="current >= totalPages" aria-label="下一页" @click="go(current + 1)">›</button>
    <select v-if="sizes.length" class="page-size-select" :value="pageSize" @change="onSizeChange">
      <option v-for="s in sizes" :key="s" :value="s">{{ s }} 条/页</option>
    </select>
  </div>
  <div v-else-if="showTotal" class="pagination">
    <span class="page-info">共 {{ total }} 条</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  total: { type: [Number, String], default: 0 },
  current: { type: [Number, String], default: 1 },
  pageSize: { type: [Number, String], default: 20 },
  sizes: { type: Array, default: () => [] }, // 如 [10, 20, 50, 100]，空数组则不显示每页条数选择
  maxVisible: { type: Number, default: 7 }, // 最多显示的页码按钮数（含省略号）
  showTotal: { type: Boolean, default: true } // 单页时是否仍显示"共 N 条"
})
const emit = defineEmits(['page-change', 'size-change'])

const totalNum = computed(() => Number(props.total) || 0)
const currentNum = computed(() => Number(props.current) || 1)
const pageSizeNum = computed(() => Number(props.pageSize) || 20)
const totalPages = computed(() => Math.max(1, Math.ceil(totalNum.value / pageSizeNum.value)))

// 计算可见页码（含省略号 '...'）
const visiblePages = computed(() => {
  const pages = totalPages.value
  const cur = currentNum.value
  const max = props.maxVisible
  if (pages <= max) {
    return Array.from({ length: pages }, (_, i) => i + 1)
  }
  // 始终显示首页、末页，中间显示当前页附近
  const half = Math.floor((max - 2) / 2)
  let left = cur - half
  let right = cur + half
  if (left < 2) { left = 2; right = left + max - 3 }
  if (right > pages - 1) { right = pages - 1; left = right - (max - 3) }
  const result = [1]
  if (left > 2) result.push('...')
  for (let i = left; i <= right; i++) result.push(i)
  if (right < pages - 1) result.push('...')
  result.push(pages)
  return result
})

function go(p) {
  if (p < 1 || p > totalPages.value || p === currentNum.value) return
  emit('page-change', p)
}

function onSizeChange(e) {
  emit('size-change', Number(e.target.value))
}
</script>

<style scoped>
.page-info { color: #758198; font-size: 13px; margin-right: 4px; }
.page-no {
  min-width: 32px;
  height: 32px;
  border: 1px solid #e4ebf5;
  border-radius: 6px;
  background: #fff;
  color: #526079;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0 8px;
  font-size: 13px;
  transition: background .15s, color .15s, border-color .15s;
}
.page-no:hover:not(:disabled):not(.active) {
  background: #f3f8ff;
  border-color: var(--primary);
  color: var(--primary);
}
.page-no:disabled {
  opacity: .5;
  cursor: not-allowed;
}
.page-no.active {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.page-no.ellipsis {
  border: none;
  background: transparent;
  cursor: default;
  min-width: 20px;
}
.page-size-select {
  height: 32px;
  border: 1px solid #e4ebf5;
  border-radius: 6px;
  background: #fff;
  color: #526079;
  font-size: 13px;
  padding: 0 6px;
  margin-left: 4px;
  cursor: pointer;
}
</style>
