<template>
  <div class="topbar">
    <button v-if="false" class="top-icon" type="button" aria-label="搜索">
      <Icon name="search" />
    </button>

    <button class="top-icon bell" type="button" aria-label="通知中心" @click="toggleNoticePanel">
      <span v-if="unreadCount > 0">{{ unreadCount }}</span>
      <Icon name="bell" />
    </button>

    <button class="top-icon" type="button" aria-label="关于我们" title="关于我们" @click="openHelp">
      <Icon name="help" />
    </button>

    <button
      class="top-icon"
      type="button"
      :aria-label="isFullscreen ? '退出全屏' : '进入全屏'"
      @click="toggleFullscreen"
    >
      <Icon name="fullscreen" />
    </button>

    <div class="top-user-wrap">
      <button class="top-user" type="button" @click="$emit('open-profile-center')">
        <div class="avatar small avatar-img"></div>
        <span>{{ displayName }}</span>
        <em>{{ sseLabel }}</em>
        <b aria-hidden="true">⌄</b>
      </button>

      <div class="top-user-menu logout-only">
        <button type="button" @click="$emit('logout')">退出登录</button>
      </div>
    </div>

    <div v-if="showNoticePanel" class="notice-panel" role="dialog" aria-label="通知中心">
      <div class="notice-panel-head">
        <h3>通知中心</h3>
        <button class="modal-close" type="button" aria-label="关闭" @click="showNoticePanel = false">
          <Icon name="close" />
        </button>
      </div>

      <div class="notice-panel-body">
        <EmptyState
          v-if="recentEvents.length === 0"
          icon="🔔"
          title="暂无通知"
          description="系统实时事件会在此显示。"
        />
        <button v-for="(ev, i) in recentEvents" :key="eventKey(ev, i)" type="button" class="notice-item" @click="onNoticeClick(ev)">
          <b>{{ ev.title || ev.type || '事件' }}</b>
          <span>{{ ev.content || ev.message || '' }}</span>
          <small>{{ ev.time || '' }}</small>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import EmptyState from './EmptyState.vue'

const props = defineProps({
  user: { type: Object, default: () => ({}) },
  sseStatus: { type: String, default: 'disconnected' },
  unreadCount: { type: [String, Number], default: 0 }
})

defineEmits(['logout', 'open-profile-center'])

const displayName = computed(() => props.user?.username || props.user?.displayName || props.user?.name || '管理员')
const sseLabel = computed(() => ({
  connected: '在线',
  connecting: '连接中',
  reconnecting: '重连中',
  disconnected: '离线',
  failed: '连接失败',
}[props.sseStatus] || '状态未知'))

function eventKey(event, index) {
  return event?.id || event?.eventId || `${event?.type || 'event'}:${event?.time || ''}:${index}`
}

const showNoticePanel = ref(false)
const recentEvents = ref([])
const isFullscreen = ref(false)

function toggleNoticePanel() {
  showNoticePanel.value = !showNoticePanel.value
}

function onSseEvent(event) {
  const detail = event.detail || {}
  recentEvents.value.unshift({
    type: detail.type || detail.eventType,
    title: detail.title || detail.eventType,
    content: detail.content || detail.message,
    time: new Date().toLocaleTimeString(),
    raw: detail
  })
  if (recentEvents.value.length > 50) recentEvents.value.pop()
}

function onNoticeClick(ev) {
  const routeMap = {
    message: 'messages',
    order: 'auto-delivery',
    account: 'accounts',
    workflow: 'logs'
  }
  const key = Object.keys(routeMap).find(item => (ev.type || '').toLowerCase().includes(item))
  if (!key) return
  location.hash = `#/${routeMap[key]}`
  showNoticePanel.value = false
}

function openHelp() {
  location.hash = '#/settings-about'
}

function toggleFullscreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen()
    return
  }
  document.documentElement.requestFullscreen().catch(() => {})
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

onMounted(() => {
  window.addEventListener('xya-sse-event', onSseEvent)
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-sse-event', onSseEvent)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<style scoped>
.top-user-wrap {
  position: relative;
}

.top-user-menu {
  position: absolute;
  right: 0;
  top: 46px;
  background: #fff;
  border: 1px solid #e8eef8;
  border-radius: 14px;
  box-shadow: 0 18px 40px rgba(30, 52, 92, 0.14);
  padding: 8px;
  z-index: 20;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-6px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.top-user-wrap:hover .top-user-menu,
.top-user-wrap:focus-within .top-user-menu {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.top-user-menu button {
  white-space: nowrap;
  border: 0;
  background: transparent;
  padding: 10px 18px;
  border-radius: 10px;
  cursor: pointer;
  color: #ef4444;
  font-weight: 800;
}

.top-user-menu button:hover {
  background: #fff5f5;
}

.notice-panel {
  position: absolute;
  right: 0;
  top: 46px;
  width: 360px;
  max-height: 480px;
  background: #fff;
  border: 1px solid var(--line, #e7edf7);
  border-radius: 14px;
  box-shadow: 0 18px 40px rgba(30, 52, 92, 0.14);
  z-index: 40;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.notice-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #eef3fa;
}

.notice-panel-head h3 {
  margin: 0;
  font-size: 16px;
}

.notice-panel-body {
  overflow: auto;
  padding: 8px;
}

.notice-item {
  display: block;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}

.notice-item:hover {
  background: #f3f8ff;
}

.notice-item b {
  display: block;
  font-size: 14px;
  color: #16213e;
}

.notice-item span {
  display: block;
  color: #667085;
  font-size: 13px;
  margin-top: 3px;
}

.notice-item small {
  color: #98a2b3;
  font-size: 11px;
}

.modal-close {
  border: 0;
  background: transparent;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
</style>
