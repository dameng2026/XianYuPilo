import { showLegalNotice } from '../../utils/legalNotice.js'

const asset = path => `/xya/${path}`

function strokeIcon(paths) {
  return `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`
}

function fillIcon(paths) {
  return `<svg class="ui-icon" viewBox="0 0 24 24" fill="currentColor">${paths}</svg>`
}

export const authIcons = {
  globe: strokeIcon('<circle cx="12" cy="12" r="9"/><path d="M12 3c2.5 2.4 4 5.7 4 9s-1.5 6.6-4 9c-2.5-2.4-4-5.7-4-9s1.5-6.6 4-9M4 12h16"/>'),
  chevronDown: strokeIcon('<path d="m7 10 5 5 5-5"/>'),
  chevronRight: strokeIcon('<path d="m10 7 5 5-5 5"/>'),
  arrowLeft: strokeIcon('<path d="M19 12H5m6-6-6 6 6 6"/>'),
  user: strokeIcon('<path d="M5 20c1.4-3.7 4.3-5.6 7-5.6s5.6 1.9 7 5.6"/><circle cx="12" cy="8" r="3.5"/>'),
  phone: strokeIcon('<rect x="7.2" y="2.6" width="9.6" height="18.8" rx="2.4"/><path d="M10 5.6h4M11.6 18.2h.8"/>'),
  code: strokeIcon('<path d="M12 3 5 6.6V12c0 4.1 2.7 7.9 7 9.2 4.3-1.3 7-5.1 7-9.2V6.6L12 3Z"/><path d="m9.4 12.1 1.8 1.8 3.6-3.8"/>'),
  lock: strokeIcon('<rect x="5.2" y="10.2" width="13.6" height="9.8" rx="2.3"/><path d="M8.4 10.2V7.9a3.6 3.6 0 1 1 7.2 0v2.3"/>'),
  layers: strokeIcon('<path d="m12 4 7 4-7 4-7-4 7-4Zm7 8-7 4-7-4m14 4-7 4-7-4"/>'),
  chart: strokeIcon('<path d="M5 18V9m5 9V6m5 12v-7m4 7H3"/>'),
  robot: strokeIcon('<rect x="6.4" y="8" width="11.2" height="8.8" rx="2.8"/><path d="M12 4.6v2.2M8.6 4.6H8m8 0h-.6M9.4 12h.1m5 0h.1M9 16h6"/>'),
  shield: strokeIcon('<path d="M12 3.2 5.4 6.7V12c0 4.3 2.7 8.1 6.6 9.4 3.9-1.3 6.6-5.1 6.6-9.4V6.7L12 3.2Z"/><path d="m9.3 12.2 1.8 1.8 3.6-3.9"/>'),
  check: strokeIcon('<circle cx="12" cy="12" r="9"/><path d="m8.7 12.2 2.2 2.2 4.5-4.8"/>'),
  eye: strokeIcon('<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6Z"/><circle cx="12" cy="12" r="2.8"/>'),
  eyeOff: strokeIcon('<path d="m4 4 16 16"/><path d="M10.6 6.4c.5-.1.9-.2 1.4-.2 6.4 0 10 5.8 10 5.8a17 17 0 0 1-3.2 3.8"/><path d="M6.5 7.3C4 9 2 12 2 12s3.6 6 10 6c1.7 0 3.2-.4 4.6-1"/>'),
  close: strokeIcon('<path d="M6 6 18 18M18 6 6 18"/>'),
  spark: strokeIcon('<path d="m12 3 1.8 4.9L19 9.7l-5.2 1.8L12 17l-1.8-5.5L5 9.7l5.2-1.8L12 3Z"/>'),
  wechat: fillIcon('<path d="M8.6 6.1c-3.4 0-6.1 2.3-6.1 5.2 0 1.7.9 3.2 2.4 4.2l-.6 2.4 2.4-1.2c.6.1 1.2.2 1.9.2 3.4 0 6.1-2.3 6.1-5.2s-2.7-5.2-6.1-5.2Zm-2 4.2a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8Zm4 0a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8Z"/><path d="M16.4 10.1c-2.9 0-5.2 1.9-5.2 4.3 0 2.4 2.3 4.3 5.2 4.3.6 0 1.3-.1 1.8-.2l2 1-.5-2c1.2-.8 1.9-1.9 1.9-3.1 0-2.4-2.3-4.3-5.2-4.3Zm-1.7 3a.8.8 0 1 1 0-1.6.8.8 0 0 1 0 1.6Zm3.5 0a.8.8 0 1 1 0-1.6.8.8 0 0 1 0 1.6Z"/>'),
  qq: fillIcon('<path d="M12 4.2c-2.1 0-3.8 2.1-3.8 4.8 0 .6.1 1.1.3 1.7-.7.8-1.1 1.9-1.1 3.1 0 1.8.8 3.4 2.1 4.3l-.7 1.7c-.1.3.2.5.5.4l2.2-1.1c.2 0 .3.1.5.1s.3 0 .5-.1l2.2 1.1c.3.1.6-.1.5-.4l-.7-1.7c1.3-.9 2.1-2.5 2.1-4.3 0-1.2-.4-2.3-1.1-3.1.2-.5.3-1.1.3-1.7 0-2.7-1.7-4.8-3.8-4.8Zm-1.2 5.2a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8Zm2.4 0a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8Z"/>'),
}

export const authStats = [
  { value: '开源部署', label: '代码与配置自主可控', icon: authIcons.user },
  { value: '本地数据', label: '数据由部署环境管理', icon: authIcons.check },
  { value: '按需配置', label: '能力以实际启用模块为准', icon: authIcons.shield },
]

export const dashboardVisualLayers = [
  { key: 'chart-left', className: 'auth-visual-chart-left', src: asset('dashboard_3d/dashboard_3d_001.png') },
  { key: 'logo-main', className: 'auth-visual-logo-main', src: asset('dashboard_3d/dashboard_3d_003.png') },
  { key: 'chart-right', className: 'auth-visual-chart-right', src: asset('dashboard_3d/dashboard_3d_002.png') },
  { key: 'cube-right', className: 'auth-visual-cube-right', src: asset('security_3d/security_3d_003.png') },
  { key: 'base', className: 'auth-visual-base-main', src: asset('dashboard_3d/dashboard_3d_007.png') },
]

export const securityVisualLayers = [
  { key: 'phone-left', className: 'auth-visual-security-phone', src: asset('security_3d/security_3d_001.png') },
  { key: 'shield-main', className: 'auth-visual-security-main', src: asset('profile-center/profile-hero.png') },
  { key: 'password-right', className: 'auth-visual-security-password', src: asset('security_3d/security_3d_008.png') },
  { key: 'cube-right', className: 'auth-visual-security-cube', src: asset('security_3d/security_3d_003.png') },
]

export const loginFeatures = [
  { title: '账号集中管理', desc: '查看账号与连接状态', icon: authIcons.robot },
  { title: '运营数据概览', desc: '展示后端实际业务数据', icon: authIcons.chart },
  { title: '自动化能力', desc: '以实际启用模块为准', icon: authIcons.layers },
]

export function openLegalDoc(title) {
  showLegalNotice(title)
}
