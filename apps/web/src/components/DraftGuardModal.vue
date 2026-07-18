<template>
  <Teleport to="body">
    <div
      v-if="state.visible"
      class="draft-guard-mask"
      @click.self="chooseSave"
      @keydown="onKeydown"
    >
      <section
        ref="dialogRef"
        class="draft-guard-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="draft-guard-title"
        :aria-describedby="state.description ? 'draft-guard-desc' : undefined"
        tabindex="-1"
      >
        <div class="draft-guard-icon">📝</div>
        <h2 id="draft-guard-title">{{ state.title }}</h2>
        <p v-if="state.description" id="draft-guard-desc" class="draft-guard-desc">{{ state.description }}</p>
        <div class="draft-guard-actions">
          <AppButton type="ghost" @click="chooseDiscard">不保存</AppButton>
          <AppButton ref="saveBtnRef" type="primary" @click="chooseSave">保存草稿</AppButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import AppButton from './AppButton.vue'
import { useDraftGuardState } from '../composables/draftGuardState.js'

const { state, resolveDraftChoice } = useDraftGuardState()
const dialogRef = ref(null)
const saveBtnRef = ref(null)
let returnFocusTarget = null

// 保存 = 保留草稿并放行；不保存 = 清除草稿并放行
function chooseSave() {
  resolveDraftChoice('save')
}
function chooseDiscard() {
  resolveDraftChoice('discard')
}

function onKeydown(event) {
  if (event.key === 'Escape' || event.key === 'Enter') {
    // 无显式选择时等同保存（自动保存），避免误关丢失数据
    event.preventDefault()
    chooseSave()
  }
}

watch(
  () => state.visible,
  async visible => {
    if (visible) {
      if (!returnFocusTarget?.isConnected) {
        returnFocusTarget = document.activeElement
      }
      await nextTick()
      if (!state.visible) return
      const target = saveBtnRef.value?.$el || dialogRef.value
      target?.focus?.()
      return
    }
    await nextTick()
    if (state.visible) return
    const target = returnFocusTarget
    returnFocusTarget = null
    if (target?.isConnected) target.focus?.()
  },
  { flush: 'post' }
)
</script>

<style scoped>
.draft-guard-mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 36, 58, .58);
  backdrop-filter: blur(2px);
  z-index: 1002;
  display: flex;
  align-items: center;
  justify-content: center;
}
.draft-guard-modal {
  position: relative;
  width: 420px;
  background: #fff;
  border: 1px solid #e8eef8;
  border-radius: 18px;
  box-shadow: 0 28px 80px rgba(17, 35, 67, .25);
  padding: 40px 36px 28px;
  text-align: center;
  color: #18223d;
  outline: none;
}
.draft-guard-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin: 0 auto 18px;
  border-radius: 50%;
  background: #f0f7ff;
  font-size: 32px;
}
.draft-guard-modal h2 {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  text-align: center;
}
.draft-guard-desc {
  margin: 0 0 28px;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  color: #64748b;
  text-align: center;
}
.draft-guard-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
.draft-guard-actions .app-btn {
  min-width: 120px;
  height: 40px;
  font-size: 14px;
}
</style>
