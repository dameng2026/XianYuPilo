<template>
  <aside class="sidebar" :class="{ open }">
    <button class="sidebar-close" type="button" aria-label="关闭菜单" @click="$emit('close')">
      <svg viewBox="0 0 24 24" class="ui-icon"><path d="M6 6l12 12M18 6 6 18" /></svg>
    </button>
    <button type="button" class="brand brand-image" aria-label="返回首页" @click="$emit('navigate','dashboard')">
      <img src="/xya/brand/brand_004.png" alt="XianYuAssistant 闲鱼助手" class="brand-logo" />
    </button>
    <nav class="nav-scroll">
      <div v-for="group in groups" :key="group.title" class="nav-group">
        <div class="nav-title">{{ group.title }}</div>
        <button
          v-for="item in group.items"
          :key="item.key"
          :class="['nav-item', { active: isActive(item.key), child: item.child }]"
          @click="$emit('navigate', item.key)"
        >
          <span class="nav-icon"><Icon :name="item.icon" /></span>
          <span>{{ item.label }}</span>
          <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
        </button>
      </div>
    </nav>
    <button type="button" class="side-user" aria-label="打开个人中心" @click="$emit('navigate','profile')">
      <div class="avatar avatar-img"></div>
      <div class="side-user-main">
        <strong>{{ displayName }}</strong>
        <span>管理员</span>
      </div>
      <span class="online-dot"></span><span class="online-text">在线</span>
    </button>
    <button class="sidebar-logout" type="button" @click="$emit('logout')">退出登录</button>
    <div class="version">© {{ copyrightYear }} XianYuAssistant<br />v{{ APP_VERSION }}</div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { navGroups } from '../data/nav.js'
import Icon from './Icon.vue'
import { APP_VERSION, getCopyrightYear } from '../utils/appMeta.js'
defineEmits(['navigate', 'close', 'logout'])
const props = defineProps({ active: { type: String, required: true }, user: { type: Object, default: () => ({}) }, open: { type: Boolean, default: false } })
const groups = navGroups
const displayName = computed(() => props.user?.username || props.user?.displayName || props.user?.name || '管理员')
const copyrightYear = getCopyrightYear()
function isActive(key) {
  if (props.active.startsWith('settings-') && props.active !== 'settings-notify' && key === 'settings-system') return true
  return props.active === key
}
</script>
