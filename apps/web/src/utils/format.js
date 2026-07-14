export function formatNumber(value, fallback = '0') {
  if (value === null || value === undefined || value === '') return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n.toLocaleString('zh-CN') : String(value)
}

export function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '¥0.00'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value).startsWith('¥') ? String(value) : `¥${value}`
  return `¥${n.toFixed(2)}`
}

export function accountName(account) {
  return account?.accountNote || account?.nickname || account?.displayName || account?.externalUid || account?.unb || `账号 ${account?.id || ''}`
}

export function shortText(value, length = 28) {
  const text = value === null || value === undefined ? '' : String(value)
  return text.length > length ? `${text.slice(0, length)}…` : text
}

export function statusText(value, map = {}) {
  if (value === null || value === undefined || value === '') return '-'
  return map[value] || map[String(value)] || String(value)
}

export function timeText(value) {
  if (!value) return '-'
  if (typeof value === 'number') {
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString('zh-CN', { hour12: false })
  }
  return String(value).replace('T', ' ')
}
