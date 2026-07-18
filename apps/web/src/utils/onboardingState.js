/**
 * 首次登录引导清单完成状态管理。
 * 完成状态持久化在 localStorage，避免重复打扰已配置好的用户。
 */
const STORAGE_KEY = 'xya:onboarding:v2:done'
const DISMISS_KEY = 'xya:onboarding:v2:dismissed'

function readDoneKeys() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = JSON.parse(raw || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeDoneKeys(keys) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(keys))
  } catch {
    // localStorage 不可用时静默降级
  }
}

export function isOnboardingDismissed() {
  try {
    return localStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

export function dismissOnboarding() {
  try {
    localStorage.setItem(DISMISS_KEY, '1')
  } catch {
    // ignore
  }
}

export function resetOnboardingDismiss() {
  try {
    localStorage.removeItem(DISMISS_KEY)
  } catch {
    // ignore
  }
}

export function getDoneKeys() {
  return readDoneKeys()
}

export function markStepDone(key) {
  const keys = readDoneKeys()
  if (!keys.includes(key)) {
    keys.push(key)
    writeDoneKeys(keys)
  }
}

export function isStepDone(key) {
  return readDoneKeys().includes(key)
}

export function resetDoneKeys() {
  writeDoneKeys([])
}
