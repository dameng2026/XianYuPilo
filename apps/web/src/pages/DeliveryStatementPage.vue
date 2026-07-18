<template>
  <div>
    <div class="page-head">
      <div>
        <h1>发货声明</h1>
        <p>配置发货声明文案与生效范围，买家确认声明后进入正式发货流程</p>
      </div>
    </div>

    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <EmptyState
      v-if="statementLoading && statementAvailable !== true"
      icon="⏳"
      title="发货声明加载中"
      description="正在读取已保存的声明状态与文案。"
    />
    <EmptyState
      v-else-if="statementAvailable !== true"
      icon="⚠️"
      title="发货声明配置暂不可用"
      description="当前无法确认已保存的声明状态。为避免覆盖未知配置，启停、保存与预览操作均已禁用。"
    >
      <template #actions>
        <AppButton :disabled="statementLoading" @click="load">重新加载</AppButton>
      </template>
    </EmptyState>

    <div v-else class="statement-layout">
      <div class="statement-main">
        <CardPanel title="发货声明配置">
          <button
            type="button"
            class="option-line statement-toggle"
            :aria-pressed="enabled"
            :disabled="saving || statementLoading"
            @click="toggleEnabled"
          >
            <span>启用发货声明</span>
            <ToggleSwitch :on="enabled" />
          </button>
          <p class="field-desc">开启后，买家付款后系统先发送声明文案，买家确认后再进入自动发货流程</p>

          <div class="form-row" style="margin-top:16px">
            <label>生效范围</label>
            <select v-model="scope" class="input" style="width:100%">
              <option value="all">全店所有自动发货商品生效</option>
              <option value="specific">仅对单独启用声明的商品生效</option>
            </select>
          </div>

          <div class="form-row" style="margin-top:16px">
            <label>声明文案</label>
            <textarea
              ref="textareaRef"
              v-model="content"
              placeholder="请输入发货声明内容，支持插入变量..."
              rows="8"
              :disabled="!enabled"
            ></textarea>
          </div>

          <div class="var-buttons">
            <span class="var-label">插入变量：</span>
            <button
              v-for="v in variables"
              :key="v.key"
              class="var-chip"
              :disabled="!enabled"
              @click="insertVariable(v.key)"
            >
{{ v.key }}
</button>
          </div>

          <div class="form-actions">
            <AppButton type="primary" :loading="saving" @click="save">保存配置</AppButton>
            <AppButton :disabled="saving || !enabled" @click="reset">恢复默认</AppButton>
          </div>
        </CardPanel>
      </div>

      <div class="statement-side">
        <CardPanel title="预览">
          <div class="preview-box">
            <div v-if="!enabled" class="subtle" style="text-align:center;padding:20px 0">发货声明已禁用，启用后可预览效果</div>
            <div v-else-if="!previewText" class="subtle" style="text-align:center;padding:20px 0">点击下方按钮预览声明效果</div>
            <pre v-else class="preview-content">{{ previewText }}</pre>
          </div>
          <div style="margin-top:12px">
            <AppButton :disabled="!enabled" @click="refreshPreview">预览声明</AppButton>
          </div>
        </CardPanel>

        <CardPanel title="变量说明" style="margin-top:16px">
          <div class="var-desc-list">
            <div v-for="v in variables" :key="v.key" class="var-desc-item">
              <code class="var-desc-key">{{ v.key }}</code>
              <span class="var-desc-text">{{ v.desc }}</span>
            </div>
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
              <span>卖家可在发货记录页手动处理待确认记录</span>
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
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import CardPanel from '../components/CardPanel.vue'
import AppButton from '../components/AppButton.vue'
import ToggleSwitch from '../components/ToggleSwitch.vue'
import EmptyState from '../components/EmptyState.vue'
import { getDeliveryStatement, previewDeliveryStatement, saveDeliveryStatement, toggleDeliveryStatement } from '../api/autoDelivery.js'

const error = ref('')
const success = ref('')
const saving = ref(false)
const previewing = ref(false)
const statementLoading = ref(true)
const statementAvailable = ref(null)
const textareaRef = ref(null)
const previewText = ref('')

const enabled = ref(false)
const content = ref('')
const scope = ref('all')

const variables = [
  { key: '{订单编号}', desc: '订单编号' },
  { key: '{商品标题}', desc: '商品标题' },
  { key: '{买家昵称}', desc: '买家昵称' },
  { key: '{发货确认链接}', desc: '发货确认链接' }
]

const defaultContent = `订单编号：{订单编号}

您好，该订单包含的商品为虚拟商品，发货后不支持退换。如无异议，请点击下方链接确认发货。

{发货确认链接}`

async function load() {
  statementLoading.value = true
  statementAvailable.value = false
  error.value = ''
  success.value = ''
  previewText.value = ''
  try {
    const res = await getDeliveryStatement()
    const data = res?.data
    if (!data || typeof data !== 'object') throw new Error('发货声明响应无效')
    if (!Object.prototype.hasOwnProperty.call(data, 'enabled')) throw new Error('发货声明缺少启用状态')
    if (typeof data.content !== 'string') throw new Error('发货声明文案无效')
    if (!['all', 'specific'].includes(String(data.scope || ''))) throw new Error('发货声明范围无效')
    enabled.value = data.enabled === true || Number(data.enabled) === 1
    content.value = data.content
    scope.value = data.scope
    statementAvailable.value = true
  } catch (e) {
    enabled.value = false
    content.value = ''
    scope.value = 'all'
    statementAvailable.value = false
    error.value = `${e.message || '声明内容加载失败'}。重新加载成功前不会保存或切换声明状态。`
  } finally {
    statementLoading.value = false
  }
}

async function toggleEnabled() {
  if (saving.value || statementLoading.value) return
  if (statementAvailable.value !== true) {
    error.value = '发货声明配置状态未知，重新加载成功前禁止切换。'
    return
  }
  error.value = ''
  success.value = ''
  const newVal = !enabled.value
  enabled.value = newVal
  previewText.value = ''
  try {
    await toggleDeliveryStatement(newVal)
    success.value = newVal ? '发货声明已启用' : '发货声明已禁用'
  } catch (e) {
    enabled.value = !newVal
    error.value = e.message || '状态切换失败'
  }
}

function insertVariable(key) {
  const textarea = textareaRef.value
  if (!textarea) return
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const text = content.value
  content.value = text.substring(0, start) + key + text.substring(end)
  nextTick(() => {
    textarea.focus()
    textarea.selectionStart = textarea.selectionEnd = start + key.length
  })
}

async function refreshPreview() {
  if (statementAvailable.value !== true) {
    error.value = '发货声明配置状态未知，重新加载成功前禁止预览。'
    return
  }
  if (!content.value.trim()) {
    error.value = '请先输入声明文案'
    return
  }
  if (previewing.value) return
  error.value = ''
  previewing.value = true
  try {
    const res = await previewDeliveryStatement({ content: content.value, scope: scope.value })
    previewText.value = res?.data?.preview || ''
  } catch (e) {
    error.value = e.message || '预览失败'
  } finally {
    previewing.value = false
  }
}

function reset() {
  if (statementAvailable.value !== true) {
    error.value = '发货声明配置状态未知，重新加载成功前禁止修改。'
    return
  }
  content.value = defaultContent
  scope.value = 'all'
  success.value = ''
  error.value = ''
  previewText.value = ''
}

async function save() {
  if (saving.value) return
  if (statementAvailable.value !== true) {
    error.value = '发货声明配置状态未知，重新加载成功前禁止保存。'
    return
  }
  error.value = ''
  success.value = ''
  if (!content.value.trim()) {
    error.value = '请输入声明文案'
    return
  }
  saving.value = true
  try {
    await saveDeliveryStatement({
      enabled: enabled.value,
      content: content.value,
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
  if (event.detail === 'statement-preview') refreshPreview()
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

.statement-toggle {
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.statement-toggle:disabled {
  cursor: not-allowed;
  opacity: .65;
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
.var-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
}
.var-label {
  color: #667085;
  font-size: 13px;
  margin-right: 2px;
  white-space: nowrap;
}
.var-chip {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 10px;
  background: #fff;
  border: 1px solid #dbe8ff;
  border-radius: 7px;
  font-size: 12px;
  color: #2d6ae3;
  cursor: pointer;
  font-weight: 650;
  transition: all .15s;
  white-space: nowrap;
}
.var-chip:hover:not(:disabled) {
  background: #e0e8ff;
  border-color: #b8ceff;
  transform: translateY(-1px);
}
.var-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.var-desc-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.var-desc-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  background: #f5f7fa;
  border-radius: 8px;
}
.var-desc-key {
  background: #eef2f7;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: #0d6bff;
  white-space: nowrap;
}
.var-desc-text {
  color: #344054;
  font-size: 13px;
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
@media (max-width:1200px) {
  .statement-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .statement-layout > * {
    min-width: 0;
  }
  .page-head {
    padding-right: 0;
  }
}

/* ───── 移动端适配 ───── */
@media (max-width: 900px) {
  /* 页头：大字体收窄、高度自适应 */
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

  /* 主布局已在 1200px 变单列，这里收窄间距 */
  .statement-layout {
    gap: 12px;
  }

  /* 预览框内边距收窄 */
  .preview-box {
    padding: 10px;
    min-height: 64px;
  }
  .preview-content {
    font-size: 13px;
    line-height: 1.5;
  }

  /* 变量插入按钮：换行展示、点击区增大 */
  .var-buttons {
    gap: 6px;
    margin-top: 10px;
  }
  .var-label {
    font-size: 13px;
  }
  .var-chip {
    height: 34px;
    padding: 0 12px;
    font-size: 12px;
  }

  /* 变量说明列表：允许换行，避免横向溢出 */
  .var-desc-list {
    gap: 8px;
  }
  .var-desc-item {
    flex-wrap: wrap;
    gap: 8px;
    padding: 8px 10px;
  }
  .var-desc-key {
    font-size: 12px;
    padding: 2px 8px;
  }
  .var-desc-text {
    font-size: 13px;
  }

  /* 流程说明：间距收窄 */
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

  /* 关键词标签：换行展示、点击区增大 */
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

  /* 表单行与文本域内边距收窄 */
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

  /* 表单操作按钮间距收窄 */
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
