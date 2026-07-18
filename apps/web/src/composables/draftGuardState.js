import { reactive } from 'vue'

// 草稿询问弹窗全局状态（单例，与 ConfirmModal 类似的模式）
const state = reactive({
  visible: false,
  title: '是否保存草稿？',
  description: '',
})

let activeResolve = null
let activePromise = null

/**
 * 弹出草稿询问弹窗，返回 Promise<'save' | 'discard'>
 * 若已有弹窗在进行中，复用同一个 Promise，避免重复弹窗
 */
export function promptDraftChoice({ title = '是否保存草稿？', description = '' } = {}) {
  if (state.visible && activePromise) return activePromise
  activePromise = new Promise((resolve) => {
    activeResolve = resolve
    state.title = title
    state.description = description
    state.visible = true
  })
  return activePromise
}

export function resolveDraftChoice(choice) {
  const done = activeResolve
  activeResolve = null
  activePromise = null
  state.visible = false
  if (done) done(choice)
}

export function useDraftGuardState() {
  return { state, resolveDraftChoice }
}
