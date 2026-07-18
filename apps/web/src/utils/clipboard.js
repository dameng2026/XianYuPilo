/**
 * 将文本复制到剪贴板，返回 Promise<boolean> 表示是否成功。
 * 优先使用 Clipboard API，失败时回退到 execCommand。
 */
export async function copyText(text) {
  const value = String(text || '').trim()
  if (!value) return false

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // fall through to legacy path
    }
  }

  return legacyCopy(value)
}

function legacyCopy(value) {
  try {
    const textarea = document.createElement('textarea')
    textarea.value = value
    textarea.setAttribute('readonly', 'readonly')
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)
    const ok = document.execCommand('copy')
    textarea.remove()
    return ok
  } catch {
    return false
  }
}
