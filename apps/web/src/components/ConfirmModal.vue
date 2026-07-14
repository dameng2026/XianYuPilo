<template>
  <Teleport to="body">
    <div v-if="state.visible" class="global-confirm-mask" @click.self="handleMaskClick">
      <section
        ref="modalRef"
        class="global-confirm-modal"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
        :aria-labelledby="titleId"
        :aria-describedby="state.description ? descriptionId : undefined"
        @keydown="handleKeydown"
      >
        <button class="global-confirm-close" aria-label="关闭确认对话框" @click="cancel"><Icon name="close" /></button>

        <!-- 警告图标（仅 confirm/alert 类型） -->
        <div v-if="state.type !== 'prompt'" class="global-confirm-icon" :class="{ dangerous: state.dangerous }">
          <Icon :name="state.dangerous ? 'warning' : 'help'" />
        </div>

        <h2 :id="titleId">{{ state.title }}</h2>

        <p v-if="state.description" :id="descriptionId" class="global-confirm-desc">{{ state.description }}</p>

        <!-- prompt 输入框 -->
        <div v-if="state.type === 'prompt'" class="global-confirm-input-wrap">
          <input
            v-model="state.value"
            class="global-confirm-input"
            :placeholder="state.placeholder"
            @keyup.enter="doConfirm"
          />
        </div>

        <div class="global-confirm-actions">
          <AppButton v-if="state.type !== 'alert'" ref="cancelActionRef" @click="cancel">取消</AppButton>
          <AppButton
            ref="confirmActionRef"
            :type="confirmBtnType"
            @click="doConfirm"
          >
            {{ state.confirmText || (state.type === 'prompt' ? '确定' : '确认') }}
          </AppButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useConfirmState } from '../composables/confirmState.js'
import Icon from './Icon.vue'
import AppButton from './AppButton.vue'

const { state, cancel, doConfirm } = useConfirmState()

const modalRef = ref(null)
const cancelActionRef = ref(null)
const confirmActionRef = ref(null)
let previouslyFocusedElement = null
const titleId = computed(() => `global-confirm-title-${state.requestId}`)
const descriptionId = computed(() => `global-confirm-description-${state.requestId}`)
const focusableSelector = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])'
].join(',')

const confirmBtnType = computed(() => {
  if (state.dangerous) return 'danger'
  return 'primary'
})

function focusControl(control) {
  const element = control?.$el ?? control
  element?.focus?.()
}

watch(
  () => state.visible,
  async (visible) => {
    if (!visible) {
      await nextTick()
      if (previouslyFocusedElement?.isConnected) previouslyFocusedElement.focus()
      previouslyFocusedElement = null
      return
    }

    previouslyFocusedElement = document.activeElement
    await nextTick()
    const safeAction = state.type === 'alert' ? confirmActionRef.value : cancelActionRef.value
    focusControl(safeAction)
  },
  { flush: 'post' }
)

function handleMaskClick() {
  if (state.type !== 'alert') cancel()
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    cancel()
    return
  }

  trapFocus(event)
}

function trapFocus(event) {
  if (event.key !== 'Tab' || !modalRef.value) return

  const focusable = [...modalRef.value.querySelectorAll(focusableSelector)]
    .filter((element) => element.getAttribute('aria-hidden') !== 'true')
  const firstFocusable = focusable[0]
  const lastFocusable = focusable.at(-1)

  if (!firstFocusable || !lastFocusable) {
    event.preventDefault()
    modalRef.value.focus()
    return
  }

  const focusIsOutside = !modalRef.value.contains(document.activeElement)
  if (event.shiftKey && (focusIsOutside || document.activeElement === firstFocusable)) {
    event.preventDefault()
    lastFocusable.focus()
  } else if (!event.shiftKey && (focusIsOutside || document.activeElement === lastFocusable)) {
    event.preventDefault()
    firstFocusable.focus()
  }
}
</script>

<style scoped>
.global-confirm-mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 36, 58, .58);
  backdrop-filter: blur(2px);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.global-confirm-modal {
  position: relative;
  width: 420px;
  background: #fff;
  border: 1px solid #e8eef8;
  border-radius: 18px;
  box-shadow: 0 28px 80px rgba(17, 35, 67, .25);
  padding: 40px 36px 28px;
  text-align: center;
  color: #18223d;
}

.global-confirm-close {
  position: absolute;
  right: 20px;
  top: 18px;
  width: 32px;
  height: 32px;
  border: 0;
  background: transparent;
  color: #35435d;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.global-confirm-close .ui-icon {
  width: 20px;
}

.global-confirm-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin: 0 auto 18px;
  border-radius: 50%;
  background: #f0f7ff;
}

.global-confirm-icon.dangerous {
  background: #fef2f2;
}

.global-confirm-icon .ui-icon {
  width: 32px;
  height: 32px;
}

.global-confirm-modal h2 {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  text-align: center;
}

.global-confirm-desc {
  margin: 0 0 28px;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  color: #64748b;
  text-align: center;
}

.global-confirm-input-wrap {
  margin: 0 0 24px;
}

.global-confirm-input {
  width: 100%;
  height: 42px;
  padding: 0 14px;
  border: 1px solid #dce2ed;
  border-radius: 8px;
  font-size: 14px;
  color: #1e293b;
  outline: none;
  box-sizing: border-box;
  transition: border-color .2s;
}

.global-confirm-input:focus {
  border-color: #0865f4;
  box-shadow: 0 0 0 3px rgba(8, 101, 244, .1);
}

.global-confirm-input::placeholder {
  color: #94a3b8;
}

.global-confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.global-confirm-actions .app-btn {
  min-width: 120px;
  height: 40px;
  font-size: 14px;
}

@media (max-width: 900px) {
  .global-confirm-mask {
    align-items: flex-end;
    padding: 0;
  }
  .global-confirm-modal {
    width: 100% !important;
    max-width: 100vw;
    max-height: 90vh;
    overflow-y: auto;
    border-radius: 20px 20px 0 0;
    padding: 32px 20px 22px;
  }
  .global-confirm-modal h2 {
    font-size: 17px;
  }
  .global-confirm-desc {
    font-size: 13px;
    line-height: 1.7;
    margin-bottom: 22px;
  }
  .global-confirm-actions {
    flex-wrap: wrap;
  }
  .global-confirm-actions .app-btn {
    flex: 1 1 auto;
    min-width: 0;
    height: 44px;
  }
}
</style>
