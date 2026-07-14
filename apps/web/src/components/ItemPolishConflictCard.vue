<template>
  <section v-if="view" class="polish-conflict-card" role="status" aria-live="polite">
    <div class="conflict-head">
      <div>
        <strong>检测到既有擦亮任务</strong>
        <p>当前请求范围与服务端正在保留的任务范围冲突。</p>
      </div>
      <span :class="['conflict-status', `status-${view.status}`]">{{ view.statusLabel }}</span>
    </div>

    <dl class="conflict-facts">
      <div><dt>任务 ID</dt><dd><code>{{ view.taskId || '未返回' }}</code></dd></div>
      <div><dt>进度</dt><dd>{{ view.progressText }}</dd></div>
      <div><dt>结果摘要</dt><dd>{{ view.message }}</dd></div>
    </dl>

    <div class="conflict-counts">
      <span>已确认 {{ view.counts.polished }}</span>
      <span>今日已擦亮 {{ view.counts.alreadyDone }}</span>
      <span>明确失败 {{ view.counts.failed }}</span>
      <span>结果未知 {{ view.counts.unknown }}</span>
    </div>

    <ul v-if="view.results.length" class="conflict-results">
      <li v-for="result in view.results" :key="`${result.goodsId}:${result.status}`">
        <span>{{ result.title || `商品 #${result.goodsId || '-'}` }}</span>
        <b>{{ itemPolishResultText(result.status) }}</b>
        <small v-if="result.message">{{ result.message }}</small>
      </li>
    </ul>

    <p class="conflict-next"><b>下一步：</b>{{ view.nextStep }}</p>
    <p class="conflict-safety">{{ view.safetyNotice }}</p>
    <p v-if="refreshMessage" class="conflict-refresh-message">{{ refreshMessage }}</p>

    <div class="conflict-actions">
      <button
        type="button"
        class="link"
        :disabled="refreshing || !view.canRefresh"
        @click="emit('refresh')"
      >
        {{ refreshing ? '正在刷新...' : '刷新已有任务状态' }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { itemPolishConflictCardState, itemPolishResultText } from '../utils/itemPolishState.js'

const props = defineProps({
  conflict: { type: Object, default: null },
  refreshing: { type: Boolean, default: false },
  refreshMessage: { type: String, default: '' },
})
const emit = defineEmits(['refresh'])
const view = computed(() => itemPolishConflictCardState(props.conflict))
</script>

<style scoped>
.polish-conflict-card {
  display: grid;
  gap: 12px;
  margin: 14px 0;
  padding: 16px;
  border: 1px solid #f4c56a;
  border-radius: 12px;
  background: #fffaf0;
  color: #344054;
}

.conflict-head,
.conflict-actions,
.conflict-results li {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.conflict-head p,
.conflict-next,
.conflict-safety,
.conflict-refresh-message {
  margin: 4px 0 0;
}

.conflict-head p,
.conflict-safety {
  color: #667085;
}

.conflict-status {
  flex: none;
  padding: 4px 9px;
  border-radius: 999px;
  background: #fff0c2;
  color: #8a5700;
  font-size: 12px;
  font-weight: 700;
}

.status-completed { background: #dcfae6; color: #067647; }
.status-failed,
.status-unknown { background: #fee4e2; color: #b42318; }
.status-partial,
.status-needs_verification { background: #fef0c7; color: #b54708; }

.conflict-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.conflict-facts div {
  min-width: 0;
  padding: 10px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.8);
}

.conflict-facts dt {
  margin-bottom: 4px;
  color: #667085;
  font-size: 12px;
}

.conflict-facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.conflict-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.conflict-counts span {
  padding: 5px 8px;
  border-radius: 7px;
  background: #fff;
  font-size: 12px;
}

.conflict-results {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.conflict-results li {
  flex-wrap: wrap;
  padding-top: 6px;
  border-top: 1px solid rgba(180, 132, 35, 0.18);
}

.conflict-results li span { min-width: 0; overflow-wrap: anywhere; }
.conflict-results li b { flex: none; color: #8a5700; font-size: 12px; }
.conflict-results li small { flex-basis: 100%; color: #667085; }
.conflict-next { color: #694100; }
.conflict-safety { font-size: 12px; }
.conflict-refresh-message { color: #b54708; font-size: 12px; }
.conflict-actions { justify-content: flex-end; }

@media (max-width: 900px) {
  .conflict-facts { grid-template-columns: 1fr; }
}
</style>
