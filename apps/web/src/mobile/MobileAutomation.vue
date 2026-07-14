<template>
  <div class="m-auto">
    <div class="m-page-header">
      <h1>自动化中心</h1>
      <p class="m-page-sub">开源版保留自动发货、自动回复、定时任务和发货记录。</p>
    </div>

    <div class="m-summary-card">
      <div class="m-summary-icon">
        <MIcon name="bot" :size="22" />
      </div>
      <div class="m-summary-copy">
        <strong>自动化能力按当前配置运行</strong>
        <span>移动端聚合已接入的运营功能，复杂规则与密钥配置建议切到桌面版处理。</span>
      </div>
    </div>

    <div class="m-section">
      <div class="m-section-header">
        <h2>核心能力</h2>
      </div>
      <div class="m-auto-grid">
        <button class="m-auto-item" @click="$emit('navigate', 'auto-delivery')">
          <div class="m-auto-icon m-auto-green">
            <MIcon name="truck" :size="26" />
          </div>
          <div class="m-auto-title">自动发货</div>
          <div class="m-auto-desc">配置订单、模板和发货链路并核对执行结果</div>
          <MIcon name="chevronRight" :size="16" class="m-auto-arrow" />
        </button>

        <button class="m-auto-item" @click="$emit('navigate', 'auto-reply')">
          <div class="m-auto-icon m-auto-purple">
            <MIcon name="reply" :size="26" />
          </div>
          <div class="m-auto-title">自动回复</div>
          <div class="m-auto-desc">配置消息规则、商品范围和话术</div>
          <MIcon name="chevronRight" :size="16" class="m-auto-arrow" />
        </button>

        <button class="m-auto-item" @click="$emit('navigate', 'scheduled-tasks')">
          <div class="m-auto-icon m-auto-orange">
            <MIcon name="clock" :size="26" />
          </div>
          <div class="m-auto-title">定时任务</div>
          <div class="m-auto-desc">定时执行运营动作和巡检任务</div>
          <MIcon name="chevronRight" :size="16" class="m-auto-arrow" />
        </button>

        <button class="m-auto-item" @click="$emit('navigate', 'delivery-records')">
          <div class="m-auto-icon m-auto-blue">
            <MIcon name="package" :size="26" />
          </div>
          <div class="m-auto-title">发货记录</div>
          <div class="m-auto-desc">查看发货历史、补发和失败原因</div>
          <MIcon name="chevronRight" :size="16" class="m-auto-arrow" />
        </button>
      </div>
    </div>

    <div class="m-section">
      <div class="m-section-header">
        <h2>配套模块</h2>
      </div>
      <div class="m-menu-list">
        <button class="m-menu-item" @click="$emit('navigate', 'card-warehouse')">
          <div class="m-menu-icon m-menu-violet">
            <MIcon name="box" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">卡密仓库</div>
            <div class="m-menu-desc">数字商品库存和卡密状态管理</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </button>

        <button class="m-menu-item" @click="$emit('navigate', 'connections')">
          <div class="m-menu-icon m-menu-sky">
            <MIcon name="activity" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">连接管理</div>
            <div class="m-menu-desc">查看账号连接、心跳与重连状态</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </button>

        <button class="m-menu-item" @click="$emit('navigate', 'accounts')">
          <div class="m-menu-icon m-menu-mint">
            <MIcon name="user" :size="20" />
          </div>
          <div class="m-menu-info">
            <div class="m-menu-title">账号管理</div>
            <div class="m-menu-desc">扫码登录、Cookie 更新和账号巡检</div>
          </div>
          <MIcon name="chevronRight" :size="16" class="m-menu-arrow" />
        </button>
      </div>
    </div>

    <div class="m-pc-notice">
      <div class="m-pc-notice-icon">
        <MIcon name="warning" :size="24" />
      </div>
      <div class="m-pc-notice-content">
        <div class="m-pc-notice-title">桌面版提供完整配置体验</div>
        <div class="m-pc-notice-desc">规则配置、模型管理、知识库和系统设置建议在桌面端完成，移动端更适合巡检和查看状态。</div>
      </div>
    </div>

    <button class="m-big-btn" @click="$emit('force-desktop')">
      <MIcon name="desktop" :size="18" />进入桌面版配置
    </button>

    <div class="m-safe-bottom"></div>
  </div>
</template>

<script setup>
import MIcon from './MIcon.vue'

defineEmits(['navigate', 'force-desktop'])
</script>

<style scoped>
.m-auto {
  padding: 12px 16px 0;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  overflow-x: hidden;
}

.m-page-header {
  margin-bottom: 16px;
}

.m-page-header h1 {
  margin: 0 0 4px;
  font-size: 26px;
  font-weight: 800;
  color: #15213d;
}

.m-page-sub {
  margin: 0;
  font-size: 13px;
  color: #8c98ae;
}

.m-summary-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 16px;
  margin-bottom: 16px;
  border-radius: 16px;
  background: linear-gradient(135deg, #fdf4e7, #fff8ef);
  border: 1px solid rgba(247, 186, 79, 0.28);
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
}

.m-summary-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(135deg, #ffcf70, #ff9f43);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.m-summary-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #6f4a14;
}

.m-summary-copy strong {
  font-size: 15px;
  color: #5a3710;
}

.m-summary-copy span {
  font-size: 13px;
  line-height: 1.6;
}

.m-section {
  margin-bottom: 16px;
}

.m-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.m-section-header h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 800;
  color: #15213d;
  min-width: 0;
}

.m-auto-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.m-auto-item,
.m-menu-item {
  width: 100%;
  border: none;
  text-align: left;
  cursor: pointer;
  min-width: 0;
}

.m-auto-item {
  position: relative;
  padding: 14px;
  min-height: 44px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
  border: 1px solid #f0f4fa;
  overflow: hidden;
}

.m-auto-icon {
  width: 50px;
  height: 50px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.m-auto-green { background: linear-gradient(135deg, #d7f8e7, #c0f1d6); color: #12a160; }
.m-auto-purple { background: linear-gradient(135deg, #efe5ff, #dfd0ff); color: #7c46ff; }
.m-auto-orange { background: linear-gradient(135deg, #fff0d8, #ffe0bf); color: #eb7b16; }
.m-auto-blue { background: linear-gradient(135deg, #dff0ff, #cae5ff); color: #0d6bff; }

.m-auto-title {
  font-size: 15px;
  font-weight: 700;
  color: #15213d;
  margin-bottom: 6px;
}

.m-auto-desc {
  font-size: 12px;
  line-height: 1.5;
  color: #7d8aa2;
  min-height: 36px;
}

.m-auto-arrow {
  position: absolute;
  right: 12px;
  top: 14px;
  color: #c2cad8;
}

.m-menu-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.m-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  min-height: 44px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
  border: 1px solid #f0f4fa;
}

.m-menu-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.m-menu-violet { background: linear-gradient(135deg, #efe6ff, #e3d7ff); color: #7c46ff; }
.m-menu-sky { background: linear-gradient(135deg, #e3f5ff, #d1eaff); color: #0d6bff; }
.m-menu-mint { background: linear-gradient(135deg, #dff8f1, #cdf1e7); color: #13a36b; }

.m-menu-info {
  flex: 1;
  min-width: 0;
}

.m-menu-title {
  font-size: 15px;
  font-weight: 700;
  color: #15213d;
  margin-bottom: 4px;
}

.m-menu-desc {
  font-size: 12px;
  color: #7d8aa2;
  line-height: 1.5;
}

.m-menu-arrow {
  color: #c2cad8;
}

.m-pc-notice {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  margin-top: 10px;
  border-radius: 16px;
  background: linear-gradient(135deg, #eff6ff, #f6f9ff);
  border: 1px solid rgba(13, 107, 255, 0.1);
  box-shadow: 0 2px 8px rgba(31, 53, 94, 0.05);
}

.m-pc-notice-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(135deg, #d8e9ff, #bfd9ff);
  color: #0d6bff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.m-pc-notice-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.m-pc-notice-title {
  font-size: 15px;
  font-weight: 700;
  color: #15213d;
}

.m-pc-notice-desc {
  font-size: 12px;
  color: #72809a;
  line-height: 1.6;
}

.m-big-btn {
  width: 100%;
  min-height: 48px;
  margin-top: 16px;
  border: none;
  border-radius: 16px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #0d6bff, #35a2ff);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  box-shadow: 0 6px 18px rgba(13, 107, 255, 0.25);
  cursor: pointer;
}

.m-safe-bottom {
  height: 100px;
}

@media (max-width: 360px) {
  .m-auto { padding: 10px 12px 0; }
  .m-page-header h1 { font-size: 22px; }
  .m-page-sub { font-size: 12px; }
  .m-summary-card { padding: 14px; gap: 10px; }
  .m-summary-copy strong { font-size: 14px; }
  .m-summary-copy span { font-size: 12px; }
  .m-section { margin-bottom: 14px; }
  .m-section-header h2 { font-size: 16px; }
  .m-auto-grid { gap: 8px; }
  .m-auto-item { padding: 12px; }
  .m-auto-icon { width: 44px; height: 44px; border-radius: 13px; }
  .m-auto-title { font-size: 14px; }
  .m-auto-desc { font-size: 11px; min-height: 32px; }
  .m-menu-item { padding: 12px; gap: 10px; }
  .m-menu-icon { width: 40px; height: 40px; border-radius: 12px; }
  .m-menu-title { font-size: 14px; }
  .m-menu-desc { font-size: 11px; }
  .m-menu-list { gap: 8px; }
}
</style>
