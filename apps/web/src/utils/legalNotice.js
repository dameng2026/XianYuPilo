let activeDialog = null

export function showLegalNotice(title = '相关协议') {
  activeDialog?.remove()

  const dialog = document.createElement('dialog')
  dialog.className = 'xya-legal-notice'
  dialog.setAttribute('aria-labelledby', 'xya-legal-notice-title')

  const heading = document.createElement('h1')
  heading.id = 'xya-legal-notice-title'
  heading.textContent = String(title || '相关协议')

  const message = document.createElement('p')
  message.textContent = `部署方尚未配置正式${heading.textContent}。商用上线前，请由部署主体提供并公示经审核的正式文本。`

  const close = document.createElement('button')
  close.type = 'button'
  close.textContent = '我知道了'
  close.addEventListener('click', () => dialog.close())
  dialog.addEventListener('close', () => {
    dialog.remove()
    if (activeDialog === dialog) activeDialog = null
  })

  dialog.append(heading, message, close)
  document.body.appendChild(dialog)
  activeDialog = dialog
  if (typeof dialog.showModal === 'function') dialog.showModal()
  else dialog.setAttribute('open', 'open')
}
