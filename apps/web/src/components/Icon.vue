<template>
  <img v-if="src" class="ui-icon ui-icon-img" :src="src" :alt="name" aria-hidden="true" />
  <TrustedSvg v-else class="ui-icon" :markup="svg" />
</template>

<script setup>
import { computed } from 'vue'
import TrustedSvg from './TrustedSvg.vue'
const props = defineProps({ name: { type: String, default: 'circle' } })
const asset = (path) => `/xya/${path}`
const pngIcons = {
  dashboard: asset('sidebar_icons/sidebar_icons_008.png'),
  data: asset('sidebar_icons/sidebar_icons_004.png'),
  board: asset('sidebar_icons/sidebar_icons_002.png'),
  account: asset('sidebar_icons/sidebar_icons_005.png'),
  users: asset('metric_icons/metric_icons_001.png'),
  link: asset('sidebar_icons/sidebar_icons_009.png'),
  product: asset('sidebar_icons/sidebar_icons_010.png'),
  publish: asset('sidebar_icons/sidebar_icons_012.png'),
  opportunity: asset('metric_icons/metric_icons_010.png'),
  message: asset('sidebar_icons/sidebar_icons_011.png'),
  chat: asset('sidebar_icons/sidebar_icons_022.png'),
  workflow: asset('workflow_assets/workflow_assets_001.png'),
  task: asset('sidebar_icons/sidebar_icons_020.png'),
  key: asset('metric_icons/metric_icons_012.png'),
  truck: asset('sidebar_icons/sidebar_icons_025.png'),
  record: asset('sidebar_icons/sidebar_icons_026.png'),
  clock: asset('workflow_assets/workflow_assets_002.png'),
  reply: asset('sidebar_icons/sidebar_icons_027.png'),
  log: asset('sidebar_icons/sidebar_icons_033.png'),
  bell: asset('brand/brand_007.png'),
  settings: asset('brand/brand_011.png'),
  search: asset('brand/brand_010.png'),
  help: asset('brand/brand_008.png'),
  fullscreen: asset('brand/brand_013.png'),
  plus: asset('brand/brand_012.png'),
  refresh: asset('brand/brand_009.png'),
  scan: asset('sidebar_icons/sidebar_icons_006.png'),
  play: asset('workflow_assets/workflow_assets_019.png'),
  save: asset('utility_icons/utility_icons_005.png'),
  shield: asset('security_3d/security_3d_011.png'),
  warning: asset('channel_icons/channel_icons_018.png'),
  map: asset('utility_icons/utility_icons_010.png'),
  ai: asset('workflow_assets/workflow_assets_042.png'),
  eye: asset('utility_icons/utility_icons_022.png'),
  close: asset('brand/brand_015.png'),
  copy: asset('utility_icons/utility_icons_017.png'),
  filter: asset('utility_icons/utility_icons_015.png'),
  upload: asset('utility_icons/utility_icons_007.png'),
  download: asset('utility_icons/utility_icons_008.png'),
  success: asset('channel_icons/channel_icons_016.png'),
  error: asset('channel_icons/channel_icons_017.png'),
  circle: asset('workflow_assets/workflow_assets_023.png'),
  aboutHero: asset('illustrations/about-hero.svg'),
  aboutVersion: asset('utility_icons/utility_icons_003.png'),
  aboutStatus: asset('channel_icons/channel_icons_016.png'),
  aboutUpdate: asset('workflow_assets/workflow_assets_002.png'),
  aboutSupportWeb: asset('sidebar_icons/sidebar_icons_008.png'),
  aboutSupportDoc: asset('sidebar_icons/sidebar_icons_011.png'),
  aboutSupportChat: asset('sidebar_icons/sidebar_icons_022.png'),
  aboutSupportFeedback: '/xya/illustrations/about-feedback.svg',
  aboutShield: asset('security_3d/security_3d_011.png'),
  aboutEye: asset('utility_icons/utility_icons_022.png'),
  notifyChannel: asset('metric_icons/metric_icons_020.png'),
  notifyEvent: asset('metric_icons/metric_icons_010.png'),
  notifyClock: asset('dashboard_3d/dashboard_3d_005.png'),
  notifyRate: asset('chat_ui_assets/chat_ui_assets_020.png'),
  notifyAlert: asset('channel_icons/channel_icons_018.png'),
  notifyHealth: asset('security_3d/security_3d_011.png'),
  notifyWebhook: asset('channel_icons/channel_icons_001.png'),
  notifyFeishu: asset('channel_icons/channel_icons_011.png'),
  notifyDingtalk: asset('channel_icons/channel_icons_005.png'),
  notifyWechat: asset('channel_icons/channel_icons_009.png'),
  notifyPushplus: asset('channel_icons/channel_icons_012.png'),
  notifyEmail: asset('channel_icons/channel_icons_015.png'),
  notifySms: asset('channel_icons/channel_icons_014.png'),
  notifyStatus: asset('channel_icons/channel_icons_016.png'),
  notifyOrder: asset('metric_icons/metric_icons_021.png'),
  notifyRisk: asset('notification/notification-risk.png'),
  notifyReport: asset('dashboard_3d/dashboard_3d_002.png'),
  notifyLog: asset('sidebar_icons/sidebar_icons_033.png'),
  notifyPreview: asset('chat_ui_assets/chat_ui_assets_023.png'),
  notifyMagic: asset('notification/notification-magic.png'),
  notifyPanelChannel: asset('metric_icons/metric_icons_020.png'),
  notifyPanelRules: asset('dashboard_3d/dashboard_3d_004.png'),
  notifyPanelLogs: asset('dashboard_3d/dashboard_3d_002.png'),
  notifyPanelPreview: asset('chat_ui_assets/chat_ui_assets_023.png'),
  notifySectionBasic: asset('dashboard_3d/dashboard_3d_004.png'),
  notifySectionWebhook: asset('channel_icons/channel_icons_001.png'),
  notifySectionSmtp: asset('channel_icons/channel_icons_015.png'),
  notifySectionToken: asset('metric_icons/metric_icons_023.png'),
  notifySectionTemplate: asset('notification/notification-magic.png'),
  notifySectionStrategy: asset('dashboard_3d/dashboard_3d_005.png')
}
const icons = {
  circle: '<circle cx="12" cy="12" r="9"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  refresh: '<path d="M20 6v5h-5"/><path d="M4 18v-5h5"/><path d="M19 11a7 7 0 0 0-12-4l-3 3M5 13a7 7 0 0 0 12 4l3-3"/>'
}
const src = computed(() => pngIcons[props.name] || '')
const svg = computed(() => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${icons[props.name] || icons.circle}</svg>`)
const name = computed(() => props.name)
</script>
