<template>
  <div>
    <div class="page-head">
      <div>
        <h1>发货声明</h1>
        <p>开启后，买家付款后系统先发送声明文案，买家回复"确认"后才进入自动发货流程</p>
      </div>
    </div>

    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <div v-if="loading" class="statement-loading" role="status">声明配置加载中...</div>
    <EmptyState v-else-if="loadError" variant="error" title="发货声明配置暂时无法加载" :description="loadError">
      <template #actions><AppButton @click="load">重新加载</AppButton></template>
    </EmptyState>

    <div v-else class="statement-layout">
      <div class="statement-main">
        <CardPanel title="发货声明配置">
          <div class="option-line" style="cursor:pointer" @click="toggleEnabled">
            <span>启用发货声明</span>
            <ToggleSwitch :on="enabled" />
          </div>
          <p class="field-desc">开启后，买家付款后系统先发送声明文案，买家回复"确认"后才进入自动发货流程；回复"取消"则转人工客服</p>

          <div class="form-row" style="margin-top:16px">
            <label>生效范围</label>
            <select v-model="scope" class="input" style="width:100%">
              <option value="all">全店所有自动发货商品生效</option>
              <option value="specific">仅对单独启用声明的商品生效</option>
            </select>
          </div>

          <div class="form-row" style="margin-top:16px">
            <label>声明文案（固定，不可修改）</label>
            <textarea
              ref="textareaRef"
              v-model="content"
              rows="8"
              readonly
              class="readonly-textarea"
            ></textarea>
          </div>

          <div class="readonly-notice">
            <span class="readonly-icon">🔒</span>
            <span>声明文案为系统固定模板，发送时会自动替换 <code>{订单编号}</code> 和 <code>{商品标题}</code> 为实际值。如需调整，请联系开发人员。</span>
          </div>

          <div class="form-actions">
            <AppButton type="primary" :loading="saving" :disabled="!settingsAvailable" @click="save">保存配置</AppButton>
          </div>
        </CardPanel>
      </div>

      <div class="statement-side">
        <CardPanel title="预览">
          <div class="preview-box">
            <div v-if="!enabled" class="subtle" style="text-align:center;padding:20px 0">发货声明已禁用，启用后可预览效果</div>
            <pre v-else class="preview-content">{{ previewText }}</pre>
          </div>
        </CardPanel>

        <CardPanel title="流程说明" style="margin-top:16px">
          <div class="flow-steps">
            <div class="flow-step">
              <span class="step-num">1</span>
              <span>买家付款，系统收到待发货消息</span>
            </div>
            <div class="flow-step">
              <span class="step-num">2</span>
              <span>系统自动发送声明文案给买家</span>
            </div>
            <div class="flow-step">
              <span class="step-num">3</span>
              <span>买家回复"确认" → 系统自动发货</span>
            </div>
            <div class="flow-step">
              <span class="step-num">4</span>
              <span>买家回复"取消" → 转人工客服，不发货</span>
            </div>
            <div class="flow-step">
              <span class="step-num">5</span>
              <span>卖家可在发货记录页"等待确认"标签手动处理</span>
            </div>
          </div>
        </CardPanel>

        <CardPanel title="支持的关键词" style="margin-top:16px">
          <div class="keyword-list">
            <div class="keyword-group">
              <div class="keyword-label">买家确认</div>
              <div class="keyword-tags">
                <span class="keyword-tag">确认</span>
                <span class="keyword-tag">确定</span>
                <span class="keyword-tag">好的</span>
                <span class="keyword-tag">好</span>
                <span class="keyword-tag">可以</span>
                <span class="keyword-tag">同意</span>
              </div>
            </div>
            <div class="keyword-group">
              <div class="keyword-label">买家取消</div>
              <div class="keyword-tags">
                <span class="keyword-tag cancel">取消</span>
                <span class="keyword-tag cancel">不要了</span>
                <span class="keyword-tag cancel">退款</span>
                <span class="keyword-tag cancel">退货</span>
                <span class="keyword-tag cancel">拒绝</span>
                <span class="keyword-tag cancel">不同意</span>
              </div>
            </div>
          </div>
        </CardPanel>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import CardPanel from '../components/CardPanel.vue'
import AppButton from '../components/AppButton.vue'
import ToggleSwitch from '../components/ToggleSwitch.vue'
import EmptyState from '../components/EmptyState.vue'
import { getDeliveryStatement, saveDeliveryStatement, toggleDeliveryStatement } from '../api/autoDelivery.js'

const error = ref('')
const success = ref('')
const loading = ref(true)
const loadError = ref('')
const settingsAvailable = ref(false)
const saving = ref(false)
const textareaRef = ref(null)

const enabled = ref(false)
const content = ref('')
const scope = ref('all')

// 固定声明文案模板（仅 {订单编号} 和 {商品标题} 会被替换）
const FIXED_STATEMENT_CONTENT = `订单编号：{订单编号}

您好，该订单包含的商品为虚拟商品，发货后不支持退换。如无异议，请回复【确认】。

如有异议，请回复【取消】，这边帮您转人工客服，进行退款操作`

// 预览文案（变量替换为示例值）
const previewText = computed(() => FIXED_STATEMENT_CONTENT
  .replace('{订单编号}', '2025071712345678')
  .replace('{商品标题}', '示例商品标题'))

async function load() {
  error.value = ''
  loadError.value = ''
  loading.value = true
  settingsAvailable.value = false
  try {
    const res = await getDeliveryStatement()
    const data = res?.data
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('发货声明配置响应格式异常')
    const enabledValue = data.enabled
    if (!(typeof enabledValue === 'boolean' || enabledValue === 0 || enabledValue === 1)) {
      throw new Error('发货声明启用状态响应格式异常')
    }
    if (!['all', 'specific'].includes(data.scope)) throw new Error('发货声明生效范围响应格式异常')
    enabled.value = enabledValue === true || enabledValue === 1
    scope.value = data.scope
    content.value = FIXED_STATEMENT_CONTENT
    settingsAvailable.value = true
  } catch (e) {
    loadError.value = `${e.message || '声明内容加载失败'}；配置成功加载前不会应用或覆盖任何设置。`
  } finally {
    loading.value = false
  }
}

async function toggleEnabled() {
  if (!settingsAvailable.value) return
  if (saving.value) return
  error.value = ''
  success.value = ''
  const newVal = !enabled.value
  enabled.value = newVal
  try {
    await toggleDeliveryStatement(newVal)
    success.value = newVal ? '发货声明已启用' : '发货声明已禁用'
  } catch (e) {
    enabled.value = !newVal
    error.value = e.message || '状态切换失败'
  }
}

async function save() {
  if (!settingsAvailable.value) return
  if (saving.value) return
  error.value = ''
  success.value = ''
  saving.value = true
  try {
    // 始终保存固定文案（后端校验时会接收，但实际发送时使用固定模板）
    await saveDeliveryStatement({
      enabled: enabled.value,
      content: FIXED_STATEMENT_CONTENT,
      scope: scope.value
    })
    success.value = '发货声明配置已保存'
  } catch (e) {
    error.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

function onHeaderAction(event) {
  if (event.detail === 'statement-save') save()
}

onMounted(() => {
  window.addEventListener('xya-header-action', onHeaderAction)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('xya-header-action', onHeaderAction)
})
</script>

<style scoped>
.statement-loading {
  padding: 48px;
  text-align: center;
  color: #667491;
}
.page-head {
  height: 62px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-right: 260px;
}
.page-head h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.1;
  letter-spacing: .3px;
}
.page-head p {
  margin: 10px 0 0;
  color: #667491;
  font-size: 15px;
}
.option-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
}
.statement-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 18px;
}
.statement-main {
  min-width: 0;
}
.statement-side {
  min-width: 0;
}
.preview-box {
  border: 1px solid #e8eef8;
  border-radius: 12px;
  padding: 12px;
  background: #fbfdff;
  min-height: 80px;
}
.preview-content {
  white-space: pre-wrap;
  font-family: inherit;
  margin: 0;
  color: #333;
  line-height: 1.6;
  font-size: 14px;
}
.field-desc {
  color: #667085;
  font-size: 13px;
  margin: 6px 0 0 0;
  line-height: 1.4;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-row label {
  font-size: 13px;
  font-weight: 700;
  color: #34425d;
}
.form-row textarea {
  width: 100%;
  min-height: 110px;
  padding: 12px;
  border: 1px solid #e7edf7;
  border-radius: 7px;
  font-family: inherit;
  resize: vertical;
  box-sizing: border-box;
  outline: none;
}
.form-row textarea:focus {
  border-color: #0d6bff;
  box-shadow: 0 0 0 3px rgba(13,107,255,.1);
}
.form-row textarea.readonly-textarea {
  background: #f5f7fa;
  color: #344054;
  cursor: not-allowed;
  resize: none;
  line-height: 1.7;
  font-size: 14px;
  white-space: pre-wrap;
}
.form-row textarea.readonly-textarea:focus {
  border-color: #e7edf7;
  box-shadow: none;
}
.readonly-notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 10px;
  padding: 10px 12px;
  background: #fff7e6;
  border: 1px solid #ffe7ba;
  border-radius: 8px;
  font-size: 13px;
  color: #7a5a18;
  line-height: 1.5;
}
.readonly-notice .readonly-icon {
  font-size: 14px;
  line-height: 1.5;
  flex-shrink: 0;
}
.readonly-notice code {
  background: #fff;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid #ffe0a3;
  color: #b06f00;
  font-size: 12px;
  font-family: inherit;
}
.form-actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
}
.subtle {
  color: #758198;
  font-size: 13px;
}
.success {
  background: #ecfdf3;
  color: #067647;
  border-color: #abefc6;
}
.flow-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.flow-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  color: #344054;
  line-height: 1.5;
}
.flow-step .step-num {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #0d6bff;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.keyword-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.keyword-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.keyword-label {
  font-size: 12px;
  font-weight: 700;
  color: #667085;
}
.keyword-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.keyword-tag {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: 13px;
  font-size: 12px;
  font-weight: 600;
  background: #e6f4ff;
  color: #0d6bff;
  border: 1px solid #bae0ff;
}
.keyword-tag.cancel {
  background: #fff1f0;
  color: #d4380d;
  border-color: #ffccc7;
}
@media (max-width:1200px) {
  .statement-layout {
    grid-template-columns: 1fr;
  }
  .page-head {
    padding-right: 0;
  }
}

/* ───── 移动端适配 ───── */
@media (max-width: 900px) {
  .page-head {
    height: auto;
    min-height: 48px;
    margin-bottom: 8px;
    flex-direction: column;
    align-items: flex-start;
  }
  .page-head h1 {
    font-size: 22px;
    line-height: 1.2;
  }
  .page-head p {
    margin: 6px 0 0;
    font-size: 13px;
  }
  .statement-layout {
    gap: 12px;
  }
  .preview-box {
    padding: 10px;
    min-height: 64px;
  }
  .preview-content {
    font-size: 13px;
    line-height: 1.5;
  }
  .flow-steps {
    gap: 10px;
  }
  .flow-step {
    font-size: 13px;
  }
  .flow-step .step-num {
    width: 20px;
    height: 20px;
    font-size: 11px;
  }
  .keyword-list {
    gap: 12px;
  }
  .keyword-tags {
    gap: 6px;
  }
  .keyword-tag {
    height: 28px;
    padding: 0 10px;
    font-size: 12px;
  }
  .field-desc {
    font-size: 13px;
    line-height: 1.5;
  }
  .form-row {
    gap: 6px;
  }
  .form-row label {
    font-size: 13px;
  }
  .form-row textarea {
    min-height: 100px;
    padding: 10px;
  }
  .form-actions {
    margin-top: 14px;
    gap: 8px;
    flex-wrap: wrap;
  }
  .subtle {
    font-size: 13px;
  }
}
</style>
