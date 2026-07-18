// 发布商品页草稿存取（localStorage，只保留最近一份）
const DRAFT_KEY = 'xianyu_publish_draft_v1'

export function loadPublishDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const data = JSON.parse(raw)
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null
    return data
  } catch {
    return null
  }
}

export function savePublishDraft(draft) {
  try {
    if (!draft || typeof draft !== 'object') return
    const payload = { ...draft, savedAt: Date.now() }
    localStorage.setItem(DRAFT_KEY, JSON.stringify(payload))
  } catch {
    // 存储不可用或已满时静默失败，不影响编辑流程
  }
}

export function clearPublishDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY)
  } catch {
    // 静默
  }
}

export function hasPublishDraft() {
  return loadPublishDraft() !== null
}
