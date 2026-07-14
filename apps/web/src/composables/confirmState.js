import { reactive } from 'vue'

// 全局确认弹窗状态
const state = reactive({
  visible: false,
  type: 'confirm',   // 'confirm' | 'alert' | 'prompt'
  title: '确认操作',
  description: '',
  confirmText: '',
  placeholder: '',
  dangerous: false,
  value: '',
  requestId: 0
})

const pendingRequests = []
let activeRequest = null
let activationScheduled = false

function activateNextRequest() {
  activationScheduled = false
  if (activeRequest || pendingRequests.length === 0) return

  activeRequest = pendingRequests.shift()
  const options = activeRequest.options
  state.type = options.type
  state.title = options.title
  state.description = options.description
  state.confirmText = options.confirmText
  state.placeholder = options.placeholder
  state.dangerous = options.dangerous
  state.value = options.value
  state.requestId += 1
  state.visible = true
}

function scheduleNextRequest() {
  if (activationScheduled || activeRequest || pendingRequests.length === 0) return
  activationScheduled = true
  queueMicrotask(activateNextRequest)
}

export function useConfirmState() {
  function show({
    type = 'confirm',
    title = '确认操作',
    description = '',
    confirmText = '',
    placeholder = '',
    dangerous = false,
    value = ''
  } = {}) {
    return new Promise((resolve) => {
      pendingRequests.push({
        options: { type, title, description, confirmText, placeholder, dangerous, value },
        resolve,
        settled: false
      })
      if (!activationScheduled) activateNextRequest()
    })
  }

  function confirm(title, description = '', confirmText = '', dangerous = false) {
    return show({ type: 'confirm', title, description, confirmText, dangerous })
  }

  function alert(title, description = '') {
    return show({ type: 'alert', title, description })
  }

  function prompt(title, placeholder = '', value = '') {
    return show({ type: 'prompt', title, placeholder, value })
  }

  function resolve(result) {
    if (!activeRequest || activeRequest.settled) return

    const request = activeRequest
    request.settled = true
    activeRequest = null
    state.visible = false
    request.resolve(result)
    scheduleNextRequest()
  }

  function cancel() {
    resolve(false)
  }

  function confirm_() {
    if (state.type === 'prompt') {
      resolve(state.value)
    } else {
      resolve(true)
    }
  }

  return { state, show, confirm, alert, prompt, resolve, cancel, doConfirm: confirm_ }
}

// 全局单例，供非 composable 环境（如 confirmAction.js）使用
export const globalConfirm = useConfirmState()
