<template>
  <section v-if="unknownResults.length" class="unknown-reconcile" role="status">
    <div class="reconcile-intro">
      <strong>逐项人工核对未知结果</strong>
      <p>请先在闲鱼 App 查看对应商品当天的擦亮结果，再逐项记录。系统不会批量猜测。</p>
    </div>
    <ul>
      <li v-for="result in unknownResults" :key="result.goodsId">
        <div>
          <b>{{ result.title || `商品 #${result.goodsId}` }}</b>
          <small v-if="result.message">{{ result.message }}</small>
        </div>
        <div class="reconcile-actions">
          <button
            type="button"
            class="link success-action"
            :disabled="Boolean(busyGoodsId)"
            @click="confirmOutcome(result, 'confirmed_polished')"
          >
            {{ busyGoodsId === result.goodsId ? '保存中...' : '已在闲鱼确认今天已擦亮' }}
          </button>
          <button
            type="button"
            class="link"
            :disabled="Boolean(busyGoodsId)"
            @click="confirmOutcome(result, 'confirmed_not_polished')"
          >
            {{ busyGoodsId === result.goodsId ? '保存中...' : '已在闲鱼确认今天未擦亮' }}
          </button>
        </div>
      </li>
    </ul>
    <p v-if="errorMessage" class="reconcile-error">{{ errorMessage }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { confirmAction } from '../utils/confirmAction.js'
import { itemPolishUnknownResults } from '../utils/itemPolishState.js'

const props = defineProps({
  task: { type: Object, default: null },
  busyGoodsId: { type: Number, default: 0 },
  errorMessage: { type: String, default: '' },
})
const emit = defineEmits(['reconcile'])
const unknownResults = computed(() => itemPolishUnknownResults(props.task))

async function confirmOutcome(result, outcome) {
  if (props.busyGoodsId || !result?.goodsId) return
  const polished = outcome === 'confirmed_polished'
  const target = `“${result.title || `商品 #${result.goodsId}`}”`
  const confirmed = await confirmAction({
    title: polished ? '确认该商品今天已擦亮？' : '确认该商品今天未擦亮？',
    description: polished
      ? `请确认你已在闲鱼 App 核对${target}。系统只记录本地人工结论，不会再次调用闲鱼、不会外呼，也不会生成新幂等键或处理其他商品。`
      : `请确认你已在闲鱼 App 核对${target}。为防迟到请求重复操作，本日不再自动重试，次日可新建任务；系统只记录本地人工结论，不会再次调用闲鱼或复用旧幂等键。`,
    confirmText: polished ? '确认记录为已擦亮' : '确认未擦亮并锁定本日重试',
  })
  if (!confirmed) return
  emit('reconcile', { goodsId: Number(result.goodsId), outcome })
}
</script>

<style scoped>
.unknown-reconcile {
  display: grid;
  gap: 10px;
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #f4c56a;
  border-radius: 10px;
  background: #fffaf0;
}

.reconcile-intro p,
.reconcile-intro strong,
.reconcile-error { margin: 0; }
.reconcile-intro p { margin-top: 4px; color: #667085; font-size: 12px; }
.unknown-reconcile ul { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.unknown-reconcile li { display: grid; gap: 8px; padding-top: 8px; border-top: 1px solid #f1dfb6; }
.unknown-reconcile li > div:first-child { display: grid; gap: 3px; }
.unknown-reconcile small { color: #667085; }
.reconcile-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.success-action { color: #067647; }
.reconcile-error { color: #b42318; font-size: 12px; }
</style>
