export function createDefaultAdApplicationForm() {
  return {
    positionType: 'home_carousel',
    planCode: '',
    title: '',
    landingUrl: '',
    contact: '',
    creativeImageUrl: '',
    remark: '',
  }
}

export function isCarouselPosition(positionType) {
  return String(positionType || '').toLowerCase() === 'home_carousel'
}

export function isTextPosition(positionType) {
  return String(positionType || '').toLowerCase() === 'sidebar_text'
}

export function filterAdPlansByPosition(plans, positionType) {
  return Array.isArray(plans)
    ? plans.filter(plan => String(plan?.positionType || '').toLowerCase() === String(positionType || '').toLowerCase())
    : []
}

export function sortEnabledAdPlans(rows) {
  return Array.isArray(rows)
    ? rows
      .filter(item => item?.enabled !== false)
      .sort((a, b) => (a?.sortOrder ?? 0) - (b?.sortOrder ?? 0))
    : []
}

export function syncAdPlanSelection(plans, positionType, planCode) {
  const filteredPlans = filterAdPlansByPosition(plans, positionType)
  if (!filteredPlans.length) return ''
  if (filteredPlans.some(plan => plan.code === planCode)) return planCode
  return filteredPlans[0].code || ''
}

export function selectAdPlan(plan) {
  return {
    positionType: plan?.positionType || 'home_carousel',
    planCode: plan?.code || '',
  }
}

export function formatPlanPrice(plan) {
  const priceLabel = String(plan?.priceLabel || '').trim()
  if (priceLabel) return priceLabel
  const priceYuan = String(plan?.priceYuan || '').trim()
  return priceYuan ? `￥${priceYuan}` : '价格待配置'
}

export function buildAdApplicationPayload(form, idempotencyKey = '') {
  const payload = {
    positionType: String(form?.positionType || 'home_carousel').trim(),
    planCode: String(form?.planCode || '').trim(),
    title: String(form?.title || '').trim(),
    landingUrl: String(form?.landingUrl || '').trim(),
    contact: String(form?.contact || '').trim(),
    creativeImageUrl: String(form?.creativeImageUrl || '').trim(),
    remark: String(form?.remark || '').trim(),
  }
  if (!isCarouselPosition(payload.positionType)) {
    delete payload.creativeImageUrl
  }
  if (idempotencyKey) payload.idempotencyKey = String(idempotencyKey).trim()
  return payload
}

export function normalizePaymentOrder(payload) {
  const source = payload?.data ?? payload ?? {}
  const rawStatus = source?.statusKey ?? source?.paymentStatus ?? source?.status
  const normalized = String(rawStatus ?? '').trim().toLowerCase()
  let statusKey = 'unknown'

  if (rawStatus !== '' && rawStatus !== null && rawStatus !== undefined) {
    const numericStatus = Number(rawStatus)
    if (Number.isFinite(numericStatus) && String(rawStatus).trim() !== '') {
      if (numericStatus === 1) statusKey = 'paid'
      else if (numericStatus === 2) statusKey = 'closed'
      else if (numericStatus === 3) statusKey = 'failed'
      else if (numericStatus === 0) statusKey = 'pending'
    }
  }

  if (statusKey === 'unknown') {
    if (normalized === 'paid') statusKey = 'paid'
    else if (['unpaid', 'not_paid', 'pending', 'created'].includes(normalized)) statusKey = 'pending'
    else if (['closed', 'cancelled', 'canceled', 'expired', 'refunded'].includes(normalized)) statusKey = 'closed'
    else if (['failed', 'payment_failed'].includes(normalized)) statusKey = 'failed'
  }

  const statusText = String(source?.statusText || '').trim()
  return {
    ...source,
    statusKey,
    statusText: statusText || getPaymentStatusText(statusKey),
    paid: statusKey === 'paid',
  }
}

export function getAdApplicationStatusClass(status) {
  switch (String(status || '').toLowerCase()) {
    case 'pending_payment':
      return 'is-pending-payment'
    case 'approved':
      return 'is-approved'
    case 'online':
      return 'is-online'
    case 'rejected':
      return 'is-rejected'
    case 'offline':
      return 'is-offline'
    default:
      return 'is-pending'
  }
}

export function getAdApplicationStatusText(status, fallback = '') {
  switch (String(status || '').toLowerCase()) {
    case 'pending_payment':
      return '待支付'
    case 'approved':
      return '已通过'
    case 'online':
      return '投放中'
    case 'rejected':
      return '已拒绝'
    case 'offline':
      return '已下线'
    case 'pending':
      return '待审核'
    default:
      return fallback || '状态未知'
  }
}

export function getPaymentStatusText(status, fallback = '') {
  switch (String(status || '').toLowerCase()) {
    case 'paid':
      return '已支付'
    case 'closed':
      return '已关闭'
    case 'expired':
      return '已过期'
    case 'failed':
      return '支付失败'
    case 'pending':
    case 'unpaid':
      return '待支付'
    default:
      return fallback || '状态未知'
  }
}
