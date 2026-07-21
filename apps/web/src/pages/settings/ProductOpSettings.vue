<template>
  <div class="po-page">
    <div v-if="loading" class="global-notice" role="status" aria-live="polite">配置加载中...</div>
    <div v-else-if="loadError" class="global-notice error" role="alert">
      <strong>商品运营配置暂时无法加载</strong>
      <p>{{ loadError }}</p>
      <button type="button" class="po-retry-btn" @click="load">重新加载</button>
    </div>
    <div v-else class="po-grid">
      <div class="po-main">
        <CardPanel title="自动上下架策略" desc="根据库存与销售情况自动管理商品状态">
          <div class="po-form">
            <div class="po-row po-row-toggle">
              <div>
                <strong>库存归零自动下架</strong>
                <p>商品库存为 0 时自动下架，避免买家拍下后无货可发</p>
              </div>
              <button
                type="button"
                :class="['po-switch', { on: form.autoShelfOffOnZeroStock }]"
                :aria-pressed="String(form.autoShelfOffOnZeroStock)"
                @click="form.autoShelfOffOnZeroStock = !form.autoShelfOffOnZeroStock"
              >
                <span class="po-switch-knob" />
              </button>
            </div>
          </div>
        </CardPanel>

        <div class="po-actions">
          <button
            type="button"
            class="po-save-btn"
            :disabled="saving || !settingsAvailable"
            @click="save"
          >
            {{ saving ? '保存中...' : '保存配置' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import CardPanel from '../../components/CardPanel.vue'
import { getBusinessSettings, saveBusinessSettings } from '../../api/businessSettings.js'

const loading = ref(true)
const loadError = ref('')
const settingsAvailable = ref(false)
const saving = ref(false)

const form = reactive({
  autoShelfOffOnZeroStock: true
})

async function load() {
  loading.value = true
  loadError.value = ''
  settingsAvailable.value = false
  form.autoShelfOffOnZeroStock = true
  try {
    const res = await getBusinessSettings('product-op-settings')
    const data = res?.data
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      throw new Error('商品运营配置响应格式异常')
    }
    if (data.autoShelfOffOnZeroStock !== undefined && typeof data.autoShelfOffOnZeroStock !== 'boolean') {
      throw new Error('自动上下架状态响应格式异常')
    }
    Object.keys(form).forEach(key => {
      if (data[key] !== undefined) form[key] = data[key]
    })
    settingsAvailable.value = true
  } catch (err) {
    console.error('[PO] 加载失败:', err)
    loadError.value = `${err.message || '网络异常'}；配置成功加载前不会应用或覆盖任何设置。`
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!settingsAvailable.value) return
  saving.value = true
  try {
    await saveBusinessSettings('product-op-settings', { ...form })
    showToast('商品运营配置已保存')
  } catch (err) {
    showToast('保存失败：' + (err.message || '网络错误'), true)
  } finally {
    saving.value = false
  }
}

function showToast(message, isError = false) {
  window.dispatchEvent(new CustomEvent('xya-toast', { detail: { message, isError } }))
}

onMounted(load)
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

.po-retry-btn {
  border: 0;
  border-radius: 10px;
  padding: 8px 14px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
}

@media (max-width: 900px) {
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
