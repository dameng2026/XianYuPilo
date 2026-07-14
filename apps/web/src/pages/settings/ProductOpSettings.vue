<template>
  <div class="po-page">
    <div class="global-notice capability-notice" role="status">
      当前版本尚未接入可持久恢复、带租约且能核验闲鱼平台结果的库存归零自动下架执行器。为避免把“已保存”误认为“会执行”，该能力保持禁用。
    </div>
    <div class="po-grid">
      <div class="po-main">
        <CardPanel title="自动上下架策略" desc="能力状态与上线前置条件">
          <div class="po-form">
            <div class="po-row po-row-toggle">
              <div>
                <strong>库存归零自动下架（当前不可用）</strong>
                <p>需先完成幂等任务、平台结果核验、未知结果人工复核与审计追踪后才能启用。</p>
              </div>
              <button type="button" class="po-switch" disabled aria-label="库存归零自动下架当前不可用">
                <span class="po-switch-knob" />
              </button>
            </div>
          </div>
        </CardPanel>

        <div class="po-actions">
          <button type="button" class="po-save-btn" disabled title="当前没有可生效的商品运营自动化配置">暂无可保存配置</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import CardPanel from '../../components/CardPanel.vue'
</script>

<style scoped>
.po-page { padding: 4px; }
.po-loading { padding: 40px; text-align: center; color: #6b7a90; }
.po-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }

.po-form { display: grid; gap: 16px; padding: 4px 2px; }
.po-row { display: flex; flex-direction: column; gap: 6px; }
.po-row > label { font-size: 12px; color: #6b7a90; font-weight: 600; }
.po-row-toggle { flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; }
.po-row-toggle > div { display: flex; flex-direction: column; gap: 4px; }
.po-row-toggle strong { font-size: 14px; color: #12233f; }
.po-row-toggle p { font-size: 12px; color: #6b7a90; margin: 0; }

.po-actions { display: flex; gap: 12px; margin-top: 16px; }
.po-save-btn {
  padding: 10px 20px; border-radius: 12px; border: 0; cursor: pointer;
  font-size: 13px; font-weight: 700;
  background: linear-gradient(135deg, #2563eb, #3b82f6); color: #fff;
  box-shadow: 0 8px 20px rgba(37,99,235,.22);
}
.po-save-btn:hover:not(:disabled) { transform: translateY(-1px); }
.po-save-btn:disabled { opacity: .6; cursor: not-allowed; }

.po-switch {
  width: 44px; height: 24px; border-radius: 999px; border: 0;
  background: #cbd5e1; cursor: pointer; position: relative;
  transition: background .2s; flex-shrink: 0; padding: 0;
}
.po-switch.on { background: #22c55e; }
.po-switch-knob {
  position: absolute; top: 2px; left: 2px;
  width: 20px; height: 20px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.2);
  transition: left .2s;
}
.po-switch.on .po-switch-knob { left: 22px; }

@media (max-width: 900px) {
  .po-loading {
    padding: 20px;
  }

  .po-form {
    gap: 12px;
  }

  .po-row-toggle {
    gap: 10px;
  }

  .po-save-btn {
    width: 100%;
    padding: 12px 20px;
  }

  .po-actions {
    margin-top: 12px;
  }
}
</style>
