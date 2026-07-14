export function canSubmitPublishIntent({
  accountsAvailable,
  submitting,
  hasIntent,
  outcome,
}) {
  if (accountsAvailable !== true || submitting) return false
  const status = String(outcome?.status || '')
  if (status === 'unknown' || status === 'in_progress') return false
  if (hasIntent && status === 'failed' && outcome?.retrySafe !== true) return false
  return true
}

export function captureProductAsyncContext({
  accountId,
  title,
  description,
  coverImageUrl,
  categoryRevision = 0,
} = {}) {
  return {
    accountId: String(accountId ?? ''),
    title: String(title ?? ''),
    description: String(description ?? ''),
    coverImageUrl: String(coverImageUrl ?? ''),
    categoryRevision: Number(categoryRevision) || 0,
  }
}

export function isProductAsyncRequestCurrent({
  requestVersion,
  currentVersion,
  snapshot,
  current,
  fields = ['accountId', 'title', 'description', 'coverImageUrl', 'categoryRevision'],
} = {}) {
  if (requestVersion !== currentVersion || !snapshot) return false
  const normalizedCurrent = captureProductAsyncContext(current)
  return fields.every(field => Object.is(snapshot[field], normalizedCurrent[field]))
}

export function buildPublishIntentSummary(payload, resolveAccountName = () => '') {
  const intent = payload && typeof payload === 'object' ? payload : {}
  const accountId = intent.xianyuAccountId ?? intent.accountId ?? ''
  const resolvedAccount = resolveAccountName(accountId)
  const account = resolvedAccount || (accountId ? `账号 ID ${accountId}` : '未选择')
  const title = String(intent.title || '未填写')
  const category = String(intent.category || '未选择')
  const price = String(intent.price ?? '0.00')
  const stock = Number(intent.stock ?? 0)
  return `账号：${account}\n商品：${title}\n分类：${category}\n价格：¥${price}\n库存：${Number.isFinite(stock) ? stock : '未知'}`
}

export function markPendingProductSync(storage) {
  try {
    const target = storage ?? globalThis.localStorage
    target?.setItem?.('xianyu_pending_sync', 'true')
    return { stored: true }
  } catch {
    return { stored: false }
  }
}
