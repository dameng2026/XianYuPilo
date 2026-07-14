/* global __APP_VERSION__, __APP_BUILD_DATE__ */

export const APP_VERSION = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '1.0.0'
export const APP_BUILD_DATE = typeof __APP_BUILD_DATE__ !== 'undefined' ? __APP_BUILD_DATE__ : ''

function toDate(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatBuildDate(value = APP_BUILD_DATE) {
  const date = toDate(value)
  if (!date) return '-'
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function formatReleaseLabel(value = APP_BUILD_DATE) {
  const date = toDate(value)
  if (!date) return 'RELEASE'
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  return `RELEASE · ${year}.${month}`
}

export function getCopyrightYear(value = APP_BUILD_DATE) {
  const date = toDate(value)
  return `${date?.getFullYear?.() || new Date().getFullYear()}`
}
