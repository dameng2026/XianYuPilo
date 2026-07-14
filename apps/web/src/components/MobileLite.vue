<template>
  <div class="mobile-shell">
    <header v-if="!subPage" class="m-topbar">
      <button type="button" class="m-brand" aria-label="返回移动端首页" @click="activeTab = 'home'">
        <div class="m-brand-mark">
          <span></span>
          <span></span>
        </div>
        <div class="m-brand-text">
          <div class="m-brand-name">XianYuAssistant</div>
          <div class="m-brand-sub">闲鱼助手</div>
        </div>
      </button>
      <button type="button" class="m-user" aria-label="打开个人中心" @click="activeTab = 'profile'">
        <div class="m-user-name">{{ username }}</div>
        <div class="m-user-avatar">
          <MIcon name="user" :size="22" />
        </div>
        <MIcon name="chevronRight" :size="16" class="m-user-arrow" />
      </button>
    </header>

    <!-- 子页面顶栏（带返回按钮） -->
    <header v-else class="m-topbar m-topbar-sub">
      <button class="m-back-btn" @click="backToMain">
        <MIcon name="chevronLeft" :size="22" />
        <span>返回</span>
      </button>
      <div class="m-sub-title">{{ subPageTitle }}</div>
      <button class="m-desktop-btn" @click="goDesktop">
        <MIcon name="desktop" :size="20" />
      </button>
    </header>

    <main ref="contentRef" class="m-content">
      <!-- 子页面视图 -->
      <MobileProducts
        v-if="subPage === 'products'"
        @navigate="onSubNavigate"
        @force-desktop="goDesktop"
        @back="backToMain"
      />
      <MobileAccounts
        v-else-if="subPage === 'accounts'"
        @navigate="onSubNavigate"
        @force-desktop="goDesktop"
        @back="backToMain"
      />
      <MobileData
        v-else-if="subPage === 'data'"
        @navigate="onSubNavigate"
        @force-desktop="goDesktop"
        @back="backToMain"
      />

      <!-- 主 Tab 视图 -->
      <template v-else>
        <MobileHome
          v-if="activeTab === 'home'"
          @navigate="onNavigate"
          @logout="emit('logout')"
          @force-desktop="goDesktop"
          @tab-change="switchTab"
        />
        <MobileMessages
          v-else-if="activeTab === 'message'"
          @navigate="onNavigate"
          @force-desktop="goDesktop"
        />
        <MobileAutomation
          v-else-if="activeTab === 'automation'"
          @navigate="onNavigate"
          @force-desktop="goDesktop"
        />
        <MobileProfile
          v-else-if="activeTab === 'profile'"
          :user="userInfo"
          @navigate="onNavigate"
          @logout="emit('logout')"
          @force-desktop="goDesktop"
          @tab-change="switchTab"
        />
      </template>
    </main>

    <nav v-if="!subPage" class="m-tabbar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="m-tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        <MIcon :name="tab.icon" :size="24" />
        <span>{{ tab.label }}</span>
      </button>
    </nav>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick, watch } from 'vue'
import MIcon from '../mobile/MIcon.vue'
import MobileHome from '../mobile/MobileHome.vue'
import MobileMessages from '../mobile/MobileMessages.vue'
import MobileAutomation from '../mobile/MobileAutomation.vue'
import MobileProfile from '../mobile/MobileProfile.vue'
import MobileProducts from '../mobile/MobileProducts.vue'
import MobileAccounts from '../mobile/MobileAccounts.vue'
import MobileData from '../mobile/MobileData.vue'
import { getCachedUsername } from '../utils/auth.js'
import { currentUser } from '../api/system.js'

const emit = defineEmits(['navigate', 'logout', 'force-desktop'])

const tabs = [
  { key: 'home', label: '首页', icon: 'home' },
  { key: 'message', label: '消息', icon: 'message' },
  { key: 'automation', label: '自动化', icon: 'bot' },
  { key: 'profile', label: '我的', icon: 'user' }
]

// 移动端支持的子页面：除了这3个外，其他 navigate 都跳转到 PC 端
const mobileSubPages = {
  products: '商品管理',
  accounts: '账号管理',
  data: '数据看板'
}

const activeTab = ref('home')
const subPage = ref(null)
const contentRef = ref(null)
const username = ref(getCachedUsername() || '未登录用户')
const userInfo = ref({ username: username.value })

const subPageTitle = computed(() => mobileSubPages[subPage.value] || '')

async function loadUser() {
  try {
    const res = await currentUser()
    if (res?.data) {
      userInfo.value = { ...userInfo.value, ...res.data }
      username.value = res.data.username || username.value
    }
  } catch { /* Cached username remains available while the profile API is unavailable. */ }
}

function switchTab(key) {
  if (activeTab.value === key) return
  activeTab.value = key
  nextTick(() => {
    if (contentRef.value) contentRef.value.scrollTop = 0
  })
}

function goDesktop() {
  emit('force-desktop')
}

// 处理 navigate 事件：若是移动端支持的子页面则切换到子页面视图，否则跳到桌面版
function onNavigate(pageKey) {
  if (mobileSubPages[pageKey]) {
    subPage.value = pageKey
    nextTick(() => {
      if (contentRef.value) contentRef.value.scrollTop = 0
    })
  } else {
    goPcPage(pageKey)
  }
}

// 子页面内部再次 navigate（仍优先尝试子页面，否则去桌面版）
function onSubNavigate(pageKey) {
  if (mobileSubPages[pageKey] && pageKey !== subPage.value) {
    subPage.value = pageKey
    nextTick(() => {
      if (contentRef.value) contentRef.value.scrollTop = 0
    })
  } else {
    goPcPage(pageKey)
  }
}

function backToMain() {
  subPage.value = null
  nextTick(() => {
    if (contentRef.value) contentRef.value.scrollTop = 0
  })
}

function goPcPage(pageKey) {
  emit('force-desktop')
  setTimeout(() => {
    emit('navigate', pageKey)
  }, 100)
}

watch(subPage, () => {})

onMounted(() => {
  loadUser()
})
</script>

<style scoped>
.mobile-shell {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  background: linear-gradient(180deg, #f5f8ff 0%, #f0f5ff 100%);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow-x: hidden;
}
.mobile-shell > header,
.mobile-shell > main,
.mobile-shell > nav {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.m-topbar {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(245, 248, 255, 0.92);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  padding: 12px 16px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(231, 237, 247, 0.5);
}

.m-topbar-sub {
  padding: 10px 8px 10px 4px;
}

.m-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: none;
  border: none;
  color: #15213d;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 100px;
  flex-shrink: 0;
}
.m-back-btn:active { background: rgba(13,107,255,0.08); }

.m-sub-title {
  flex: 1;
  text-align: center;
  font-size: 17px;
  font-weight: 700;
  color: #15213d;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-desktop-btn {
  background: none;
  border: none;
  color: #72809a;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}
.m-desktop-btn:active { background: rgba(13,107,255,0.08); }

.m-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
}
.m-brand-mark {
  width: 40px;
  height: 40px;
  position: relative;
  flex-shrink: 0;
}
.m-brand-mark span {
  position: absolute;
  left: 16px;
  top: 0;
  width: 12px;
  height: 43px;
  border-radius: 8px;
  background: linear-gradient(180deg, #0d7fff, #16b7ff);
  transform: rotate(42deg);
  box-shadow: 0 4px 12px rgba(13,107,255,0.25);
}
.m-brand-mark span + span {
  transform: rotate(-42deg);
  background: linear-gradient(180deg, #25a5ff, #0362f4);
}
.m-brand-name {
  font-size: 17px;
  font-weight: 800;
  color: #15213d;
  line-height: 1.2;
  letter-spacing: -0.2px;
}
.m-brand-sub {
  font-size: 11px;
  color: #72809a;
  letter-spacing: 1px;
  margin-top: 1px;
}

.m-user {
  display: flex;
  align-items: center;
  gap: 8px;
  background: white;
  border-radius: 100px;
  padding: 5px 10px 5px 14px;
  box-shadow: 0 2px 8px rgba(31,53,94,0.06);
  border: 1px solid #eef2fa;
  cursor: pointer;
  transition: transform 0.1s;
  color: inherit;
  font: inherit;
}
.m-user:active { transform: scale(0.97); }
.m-user-name {
  font-size: 14px;
  font-weight: 600;
  color: #15213d;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #ffb94a, #ff7a8a);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.m-user-arrow { color: #b0bacb; }

.m-content {
  flex: 1;
  width: 100%;
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  padding-bottom: calc(76px + env(safe-area-inset-bottom));
}

.m-tabbar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(231,237,247,0.7);
  padding: 6px 0 max(8px, env(safe-area-inset-bottom));
  display: flex;
  align-items: stretch;
  justify-content: space-around;
  z-index: 100;
  box-shadow: 0 -4px 20px rgba(31,53,94,0.05);
}
.m-tab {
  flex: 1;
  background: none;
  border: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 6px 0;
  color: #9aa7bc;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.2s;
  position: relative;
}
.m-tab :deep(svg) { transition: transform 0.2s; }
.m-tab.active {
  color: #0d6bff;
}
.m-tab.active :deep(svg) {
  transform: scale(1.08);
}
.m-tab.active::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  width: 24px;
  height: 3px;
  background: linear-gradient(90deg, #0d6bff, #3b9bff);
  border-radius: 0 0 3px 3px;
}
</style>
