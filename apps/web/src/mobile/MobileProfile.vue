<template>
  <div class="m-profile">
    <!-- 用户卡片 -->
    <div class="m-pro-hero">
      <div class="m-pro-avatar">
        <MIcon name="user" :size="32" />
      </div>
      <div class="m-pro-info">
        <div class="m-pro-name">{{ displayName }}</div>
        <div class="m-pro-desc">
          <MIcon name="shield" :size="12" /> {{ planName }}
        </div>
        <div class="m-pro-verify">
          <span class="m-pro-tag ok">
            <MIcon name="lock" :size="10" /> 固定账号密码登录
          </span>
        </div>
      </div>
    </div>

    <div v-if="overviewError" class="m-state-warning" role="alert">
      <span>{{ overviewError }}</span>
      <button type="button" @click="loadOverview">重试</button>
    </div>

    <!-- 数据统计 -->
    <div class="m-pro-stats">
      <div class="m-pro-stat" @click="$emit('navigate', 'accounts')">
        <div class="m-pro-stat-val">{{ overviewAvailable ? (stats.xianyuAccountCount ?? 0) : '—' }}</div>
        <div class="m-pro-stat-label">闲鱼账号</div>
      </div>
      <div class="m-pro-stat-div"></div>
      <div class="m-pro-stat" @click="$emit('navigate', 'products')">
        <div class="m-pro-stat-val">{{ overviewAvailable ? (stats.goodsCount ?? 0) : '—' }}</div>
        <div class="m-pro-stat-label">商品</div>
      </div>
      <div class="m-pro-stat-div"></div>
      <div class="m-pro-stat" @click="$emit('navigate', 'orders')">
        <div class="m-pro-stat-val">{{ overviewAvailable ? (stats.orderCount ?? 0) : '—' }}</div>
        <div class="m-pro-stat-label">订单</div>
      </div>
      <div class="m-pro-stat-div"></div>
      <div class="m-pro-stat" @click="$emit('tab-change', 'message')">
        <div class="m-pro-stat-val">{{ overviewAvailable ? (stats.conversationCount ?? 0) : '—' }}</div>
        <div class="m-pro-stat-label">会话</div>
      </div>
    </div>

    <!-- 账号设置 -->
    <div class="m-section">
      <div class="m-section-header">
        <h2>账号设置</h2>
      </div>
      <div class="m-menu-list">
        <div class="m-menu-item" @click="$emit('navigate', 'profile')">
          <div class="m-menu-icon" style="background:linear-gradient(135deg,#e8f1ff,#d0e2ff);color:#0d6bff">
            <MIcon name="user" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">个人中心</div>
            <div class="m-menu-desc">账号资料与安全</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </div>
        <div class="m-menu-item" @click="$emit('navigate', 'settings-notify')">
          <div class="m-menu-icon" style="background:linear-gradient(135deg,#fff4e0,#ffe7c2);color:#ff9f22">
            <MIcon name="bell" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">通知设置</div>
            <div class="m-menu-desc">消息与提醒配置</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </div>
        <div class="m-menu-item" @click="$emit('navigate', 'settings-system')">
          <div class="m-menu-icon" style="background:linear-gradient(135deg,#e2f8ee,#cdf2df);color:#16bf78">
            <MIcon name="settings" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">系统设置</div>
            <div class="m-menu-desc">AI客服、商品操作与关于</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </div>
      </div>
    </div>

    <!-- 安全设置 -->
    <div class="m-section">
      <div class="m-section-header">
        <h2>安全设置</h2>
      </div>
      <div class="m-menu-list">
        <div class="m-menu-item" @click="$emit('navigate', 'profile')">
          <div class="m-menu-icon" style="background:linear-gradient(135deg,#f0ebff,#e2d8ff);color:#8b5cf6">
            <MIcon name="lock" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">修改密码</div>
            <div class="m-menu-desc">建议定期更换密码</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </div>
      </div>
    </div>

    <!-- 其他 -->
    <div class="m-section">
      <div class="m-section-header">
        <h2>其他</h2>
      </div>
      <div class="m-menu-list">
        <div class="m-menu-item" @click="$emit('navigate', 'logs')">
          <div class="m-menu-icon" style="background:linear-gradient(135deg,#f0ebff,#e2d8ff);color:#8b5cf6">
            <MIcon name="help" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">操作日志</div>
            <div class="m-menu-desc">查看系统操作记录</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="m-pro-actions">
      <button class="m-btn m-btn-outline" @click="$emit('force-desktop')">
        <MIcon name="desktop" :size="18" />继续进入桌面版
      </button>
      <button class="m-btn m-btn-danger" @click="$emit('logout')">
        <MIcon name="logout" :size="18" />退出登录
      </button>
    </div>

    <div class="m-safe-bottom"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import MIcon from './MIcon.vue'
import { getProfileOverview } from '../api/profile.js'
import { getCachedUsername } from '../utils/auth.js'

const props = defineProps({
  user: { type: Object, default: () => ({ username: '管理员' }) }
})
defineEmits(['navigate', 'logout', 'force-desktop', 'tab-change'])

const overview = ref({})
const overviewAvailable = ref(false)
const overviewError = ref('')

const displayName = computed(() => overview.value.nickname || overview.value.username || props.user?.username || getCachedUsername() || '管理员')

const planName = computed(() => '开源自托管版')

const stats = computed(() => overview.value.stats || {})

async function loadOverview() {
  overviewError.value = ''
  try {
    const res = await getProfileOverview()
    if (res?.data) {
      overview.value = res.data
      overviewAvailable.value = true
      return
    }
    throw new Error('invalid profile response')
  } catch {
    overviewAvailable.value = false
    overviewError.value = '个人概览暂不可用；未加载的统计以“—”显示。'
  }
}

onMounted(() => {
  loadOverview()
})
</script>

<style scoped>
.m-profile {
  padding: 12px 16px 0;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  overflow-x: hidden;
}

.m-pro-hero {
  background: linear-gradient(135deg, #e8f1ff 0%, #f0f5ff 100%);
  border-radius: 16px;
  padding: 16px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 16px;
  border: 1px solid rgba(13, 107, 255, 0.08);
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
}
.m-pro-avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(135deg, #0d6bff, #3b9bff);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(13,107,255,0.3);
  flex-shrink: 0;
}
.m-pro-info { flex: 1; min-width: 0; }
.m-pro-name {
  font-size: 20px;
  font-weight: 700;
  color: #15213d;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-pro-desc {
  font-size: 12px;
  color: #72809a;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
}
.m-pro-desc :deep(svg) { color: #f0a020; }
.m-pro-verify {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.m-pro-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 3px 7px;
  border-radius: 100px;
  font-weight: 500;
}
.m-pro-tag.ok {
  background: rgba(22,191,120,0.12);
  color: #16bf78;
}
.m-pro-tag.warn {
  background: rgba(255,159,34,0.12);
  color: #ff9f22;
}
.m-state-warning {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-bottom: 16px; padding: 12px 14px; border: 1px solid #f6d58a;
  border-radius: 14px; color: #8a4b08; background: #fff8e8;
  font-size: 12px; line-height: 1.5;
}
.m-state-warning button {
  min-height: 40px; padding: 0 14px; flex-shrink: 0; border: 1px solid #e2ad3b;
  border-radius: 12px; color: #744006; background: white; font-weight: 600;
}

.m-pro-stats {
  background: white;
  border-radius: 16px;
  padding: 16px 8px;
  display: flex;
  align-items: center;
  justify-content: space-around;
  margin-bottom: 16px;
  border: 1px solid #f0f4fa;
  box-shadow: 0 2px 8px rgba(31,53,94,0.05);
}
.m-pro-stat {
  flex: 1;
  min-width: 0;
  text-align: center;
  cursor: pointer;
  padding: 8px 4px;
  min-height: 44px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.m-pro-stat-val { font-size: 22px; font-weight: 800; color: #15213d; margin-bottom: 3px; line-height: 1.2; }
.m-pro-stat-label { font-size: 12px; color: #8c98ae; font-weight: 500; }
.m-pro-stat-div {
  width: 1px;
  height: 32px;
  background: #e8edf5;
  flex-shrink: 0;
}

.m-section {
  background: white;
  border-radius: 16px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(31,53,94,0.05);
  border: 1px solid #f0f4fa;
}
.m-section-header {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.m-section-header h2 { margin: 0; font-size: 17px; font-weight: 700; color: #15213d; min-width: 0; }
.m-section-action {
  background: none;
  border: none;
  color: #0d6bff;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  padding: 4px 10px;
  min-height: 44px;
  box-sizing: border-box;
  border-radius: 100px;
  flex-shrink: 0;
}
.m-section-action:active { background: rgba(13,107,255,0.08); }

/* 菜单 */
.m-menu-list { display: flex; flex-direction: column; gap: 4px; }
.m-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 10px;
  cursor: pointer;
  border-radius: 14px;
  transition: background 0.15s;
  min-height: 56px;
  min-width: 0;
}
.m-menu-item:active { background: #f8faff; }
.m-menu-icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.m-menu-info { flex: 1; min-width: 0; }
.m-menu-title { font-size: 14px; font-weight: 600; color: #15213d; margin-bottom: 2px; }
.m-menu-desc {
  font-size: 12px;
  color: #8c98ae;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-menu-arrow { color: #c4cddb; flex-shrink: 0; }
.m-menu-status {
  font-size: 11px;
  padding: 4px 10px;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  border-radius: 100px;
  font-weight: 600;
  flex-shrink: 0;
}
.m-menu-status.ok {
  background: rgba(22,191,120,0.12);
  color: #16bf78;
}
.m-menu-status.warn {
  background: rgba(255,159,34,0.12);
  color: #ff9f22;
}

/* 操作按钮 */
.m-pro-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
}
.m-btn {
  width: 100%;
  height: 48px;
  min-width: 0;
  border-radius: 24px;
  border: none;
  font-size: 15px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: transform 0.1s;
}
.m-btn:active { transform: scale(0.98); }
.m-btn-outline {
  background: white;
  color: #0d6bff;
  border: 1.5px solid #d4e4ff;
}
.m-btn-danger {
  background: #fff5f5;
  color: #ff5252;
  border: 1.5px solid #ffd1d1;
}

.m-safe-bottom { height: 80px; }

@media (max-width: 360px) {
  .m-profile { padding: 10px 12px 0; }
  .m-pro-hero { padding: 14px; gap: 10px; }
  .m-pro-avatar { width: 52px; height: 52px; }
  .m-pro-name { font-size: 18px; }
  .m-pro-stats { padding: 14px 6px; }
  .m-pro-stat-val { font-size: 20px; }
  .m-pro-stat-label { font-size: 11px; }
  .m-section { padding: 14px; }
  .m-section-header h2 { font-size: 16px; }
  .m-menu-item { padding: 12px 8px; gap: 10px; min-height: 52px; }
  .m-menu-icon { width: 38px; height: 38px; border-radius: 10px; }
  .m-menu-title { font-size: 13px; }
  .m-menu-desc { font-size: 11px; }
}
</style>
