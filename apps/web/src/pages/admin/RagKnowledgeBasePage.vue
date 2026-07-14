<template>
  <div class="admin-rag">
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div v-if="kbsWarning" class="global-notice warning" role="status">{{ kbsWarning }}</div>
    <div v-if="success" class="global-notice success">{{ success }}</div>

    <div class="grid stat-grid" style="grid-template-columns:repeat(4,1fr)">
      <StatCard title="知识库总数" :value="kbMetric(kbStats.total)" change="全部记录" icon="document" />
      <StatCard title="启用中" :value="kbMetric(kbStats.active)" change="status=1" icon="shield" color="green" />
      <StatCard title="文档总数" :value="kbMetric(kbStats.docs)" change="所有知识库汇总" icon="product" color="orange" />
      <StatCard title="分块总数" :value="kbMetric(kbStats.chunks)" change="所有知识库汇总" icon="message" color="purple" />
    </div>

    <div class="toolbar">
      <AppButton :disabled="kbsLoading" @click="refreshKbs">{{ kbsLoading ? '刷新中...' : '刷新' }}</AppButton>
      <AppButton type="primary" :disabled="kbsAvailable !== true" @click="openCreateKb">+ 新建知识库</AppButton>
    </div>

    <CardPanel title="知识库列表" desc="管理 RAG 知识库与文档索引">
      <div v-if="kbsRefreshing" class="refresh-status" role="status" aria-live="polite">
        正在刷新知识库列表，现有数据仍可查看。
      </div>
      <EmptyState v-if="kbsLoading && kbsAvailable !== true" icon="⏳" title="知识库加载中" description="正在读取知识库与索引统计。" />
      <EmptyState v-else-if="kbsAvailable === false" icon="⚠️" title="知识库暂不可用" description="当前无法确认知识库记录；为避免覆盖未知数据，创建、编辑和删除均已禁用。">
        <template #actions><AppButton @click="refreshKbs">重新加载</AppButton></template>
      </EmptyState>
      <BaseTable v-else-if="kbsAvailable === true" :columns="kbCols" :rows="kbs">
        <template #name="{ row }"><strong>{{ row.name }}</strong></template>
        <template #description="{ row }"><span :title="row.description">{{ row.description || '-' }}</span></template>
        <template #docCount="{ row }">{{ row.docCount ?? '—' }}</template>
        <template #chunkCount="{ row }">{{ row.chunkCount ?? '—' }}</template>
        <template #embeddingModel="{ row }">{{ row.embeddingModel || '-' }}</template>
        <template #status="{ row }"><Badge :type="row.status === 1 ? 'green' : (row.status === 0 ? 'red' : 'gray')">{{ row.status === 1 ? '启用' : (row.status === 0 ? '禁用' : '状态未知') }}</Badge></template>
        <template #updatedTime="{ row }">{{ formatDateTime(row.updatedTime) }}</template>
        <template #op="{ row }">
          <button class="link" @click="openKbDetail(row)">进入</button>
          <button class="link" @click="openEditKb(row)">编辑</button>
          <button class="link" @click="openSearchKb(row)">检索测试</button>
          <button class="link danger-text" @click="removeKb(row)">删除</button>
        </template>
        <template #empty>
          <EmptyState icon="📚" title="暂无知识库" description="点击「新建知识库」开始管理你的文档。" />
        </template>
      </BaseTable>
    </CardPanel>
    <Teleport to="body">
      <div v-if="kbModal.visible" class="modal-mask" @click.self="closeKbModal">
        <section class="xy-modal" style="width:560px">
          <button class="modal-close" @click="closeKbModal"><Icon name="close" /></button>
          <h2>{{ kbModal.isEdit ? '编辑知识库' : '新建知识库' }}</h2>
          <form class="modal-form" @submit.prevent="submitKb">
            <div class="form-grid">
              <div class="form-row form-row-full">
                <label>名称 <em>*</em></label>
                <input v-model="kbModal.form.name" class="input" placeholder="如 商品FAQ" />
              </div>
              <div class="form-row form-row-full">
                <label>描述</label>
                <textarea v-model="kbModal.form.description" class="input" rows="3" placeholder="可选"></textarea>
              </div>
              <div class="form-row">
                <label>Embedding 模型</label>
                <input v-model="kbModal.form.embeddingModel" class="input" placeholder="如 text-embedding-3-small" />
              </div>
              <div class="form-row">
                <label>Embedding Base URL</label>
                <input v-model="kbModal.form.embeddingBaseUrl" class="input" placeholder="https://api.openai.com/v1" />
                <small>仅支持可解析的公网 HTTPS；切换主机时需重新输入下方 API Key。</small>
              </div>
              <div class="form-row form-row-full">
                <label>Embedding API Key</label>
                <SecretInput
                  v-model="kbModal.form.embeddingApiKey"
                  :placeholder="kbModal.form.embeddingApiKeyConfigured ? '已保存，直接输入新值可覆盖' : 'sk-...'"
                />
              </div>
              <div class="form-row">
                <label>状态</label>
                <select v-model.number="kbModal.form.status" class="input">
                  <option :value="1">启用</option>
                  <option :value="0">禁用</option>
                </select>
              </div>
            </div>
            <div class="modal-actions">
              <AppButton native-type="button" @click="closeKbModal">取消</AppButton>
              <AppButton type="primary" native-type="submit" :loading="kbModal.submitting">{{ kbModal.isEdit ? '保存' : '创建' }}</AppButton>
            </div>
          </form>
        </section>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="detailKb" class="modal-mask" @click.self="closeDetail">
        <section class="xy-modal" style="width:820px">
          <button class="modal-close" @click="closeDetail"><Icon name="close" /></button>
          <h2>知识库：{{ detailKb.name }}</h2>
          <p v-if="detailKb.description" class="subtle">{{ detailKb.description }}</p>
          <div v-if="docsError" class="global-notice error">{{ docsError }}</div>
          <div v-if="docsWarning" class="global-notice warning" role="status">{{ docsWarning }}</div>

          <div class="detail-toolbar">
            <input v-model="uploadForm.fileName" class="input" :disabled="!canMutateDocs" placeholder="手动输入文件名（如 faq.txt）" />
            <textarea v-model="uploadForm.content" class="input" :disabled="!canMutateDocs" rows="3" placeholder="输入文本内容（手动上传）"></textarea>
            <div class="detail-toolbar-row">
              <input ref="fileInput" type="file" accept=".txt,.md,text/plain,text/markdown" :disabled="!canMutateDocs" @change="onFilePick" />
              <AppButton type="primary" :loading="uploading" :disabled="uploading || !canMutateDocs" @click="uploadManual">上传文本</AppButton>
              <AppButton :loading="uploading" :disabled="uploading || !pickedFile || !canMutateDocs" @click="uploadFile">上传文件</AppButton>
              <AppButton :disabled="docsLoading" @click="loadDocs">{{ docsLoading ? '刷新中...' : '刷新' }}</AppButton>
            </div>
            <small class="upload-hint">仅支持 UTF-8 编码的 .txt / .md 文档，单个文件不超过 10MB。</small>
          </div>

          <div v-if="docsRefreshing" class="refresh-status" role="status" aria-live="polite">
            正在刷新文档列表，现有数据仍可查看。
          </div>
          <EmptyState v-if="docsLoading && docsAvailable !== true" icon="⏳" title="文档加载中" description="正在读取文档与索引状态。" />
          <EmptyState v-else-if="docsAvailable === false" icon="⚠️" title="文档列表暂不可用" description="当前无法确认已有文档；上传、删除和重建索引均已禁用。">
            <template #actions><AppButton @click="loadDocs">重新加载</AppButton></template>
          </EmptyState>
          <BaseTable v-else-if="docsAvailable === true" :columns="docCols" :rows="docs" style="margin-top:12px">
            <template #fileName="{ row }"><strong>{{ row.fileName || '-' }}</strong></template>
            <template #fileType="{ row }">{{ row.fileType || '-' }}</template>
            <template #fileSize="{ row }">{{ formatSize(row.fileSize) }}</template>
            <template #chunkCount="{ row }">{{ row.chunkCount ?? '—' }}</template>
            <template #parseStatus="{ row }">
              <div class="parse-status-cell">
                <Badge :type="parseStatusType(row.parseStatus)">{{ parseStatusText(row.parseStatus) }}</Badge>
                <small v-if="documentErrorMessage(row)" :title="documentErrorMessage(row)">{{ documentErrorMessage(row) }}</small>
              </div>
            </template>
            <template #createdTime="{ row }">{{ formatDateTime(row.createdTime) }}</template>
            <template #op="{ row }">
              <button class="link" :disabled="Number(row.chunkCount || 0) <= 0" @click="viewChunks(row)">分块</button>
              <button
                class="link"
                :disabled="reindexing === row.id || !canReindex(row)"
                :title="canReindex(row) ? '重新生成向量索引' : '该文档尚未生成分块，不可重建索引'"
                @click="reindexDoc(row)"
              >
{{ reindexing === row.id ? '索引中...' : '重建索引' }}
</button>
              <button class="link danger-text" @click="removeDoc(row)">删除</button>
            </template>
            <template #empty>
              <EmptyState icon="📄" title="暂无文档" description="通过上方文本框或文件上传添加文档。" />
            </template>
          </BaseTable>
        </section>
      </div>
    </Teleport>
    <Teleport to="body">
      <div v-if="chunksModal.visible" class="modal-mask" @click.self="chunksModal.visible = false">
        <section class="xy-modal" style="width:720px">
          <button class="modal-close" @click="chunksModal.visible = false"><Icon name="close" /></button>
          <h2>分块列表（共 {{ chunksModal.list.length }} 块）</h2>
          <div class="chunks-list">
            <div v-for="(c, i) in chunksModal.list" :key="c.id || i" class="chunk-item">
              <div class="chunk-head"><b>#{{ c.chunkIndex }}</b><span>{{ c.tokenCount || 0 }} 字符</span></div>
              <pre>{{ c.content }}</pre>
            </div>
            <EmptyState v-if="!chunksModal.list.length" icon="📦" title="暂无分块" description="该文档尚未生成任何分块。" />
          </div>
          <div class="modal-actions">
            <AppButton type="primary" @click="chunksModal.visible = false">关闭</AppButton>
          </div>
        </section>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="searchModal.visible" class="modal-mask" @click.self="searchModal.visible = false">
        <section class="xy-modal" style="width:680px">
          <button class="modal-close" @click="searchModal.visible = false"><Icon name="close" /></button>
          <h2>检索测试 - {{ searchModal.kbName }}</h2>
          <div class="search-box">
            <input v-model="searchModal.query" class="input" placeholder="输入查询文本" @keyup.enter="runSearch" />
            <AppButton type="primary" :loading="searchModal.loading" @click="runSearch">检索</AppButton>
          </div>
          <div class="search-hits">
            <EmptyState v-if="searchAvailable === false" icon="⚠️" title="检索结果暂不可用" description="本次检索失败，不会把失败显示为未命中；请检查服务后重试。" />
            <div v-for="(h, i) in searchModal.hits" :key="i" class="hit-item">
              <div class="hit-head"><b>得分 {{ h.score }}</b><span>docId: {{ h.docId }}</span></div>
              <pre>{{ h.content }}</pre>
            </div>
            <EmptyState v-if="searchAvailable === true && !searchModal.hits.length && searchModal.searched" icon="🔍" title="未命中" description="未找到相关分块，可调整查询或降低相似度阈值。" />
          </div>
          <div class="modal-actions">
            <AppButton type="primary" @click="searchModal.visible = false">关闭</AppButton>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import StatCard from '../../components/StatCard.vue'
import CardPanel from '../../components/CardPanel.vue'
import BaseTable from '../../components/BaseTable.vue'
import Badge from '../../components/Badge.vue'
import AppButton from '../../components/AppButton.vue'
import EmptyState from '../../components/EmptyState.vue'
import Icon from '../../components/Icon.vue'
import SecretInput from '../../components/SecretInput.vue'
import {
  listKnowledgeBases,
  createKnowledgeBase,
  updateKnowledgeBase,
  deleteKnowledgeBase,
  listDocuments,
  uploadDocument,
  deleteDocument,
  reindexDocument,
  listChunks,
  searchKnowledge
} from '../../api/rag.js'
import { recordsOf } from '../../utils/apiData.js'
import { confirmAction } from '../../utils/confirmAction.js'
import { createLatestRequestGuard, listRefreshRequestConfig } from '../../utils/latestRequest.js'

const error = ref('')
const success = ref('')
const kbsWarning = ref('')
const kbs = ref([])
const docs = ref([])
const kbsAvailable = ref(null)
const kbsLoading = ref(true)
const docsAvailable = ref(null)
const docsLoading = ref(false)
const docsError = ref('')
const docsWarning = ref('')
const searchAvailable = ref(null)
const detailKb = ref(null)
const uploading = ref(false)
const reindexing = ref(null)
const fileInput = ref(null)
const pickedFile = ref(null)
const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
const ALLOWED_DOCUMENT_EXTENSIONS = ['.txt', '.md']
const kbsRequestGuard = createLatestRequestGuard()
const docsRequestGuard = createLatestRequestGuard()

const kbCols = [
  { key: 'id', title: 'ID' },
  { key: 'name', title: '名称' },
  { key: 'description', title: '描述' },
  { key: 'docCount', title: '文档数' },
  { key: 'chunkCount', title: '分块数' },
  { key: 'embeddingModel', title: '嵌入模型' },
  { key: 'status', title: '状态' },
  { key: 'updatedTime', title: '更新时间' },
  { key: 'op', title: '操作' }
]

const docCols = [
  { key: 'id', title: 'ID' },
  { key: 'fileName', title: '文件名' },
  { key: 'fileType', title: '类型' },
  { key: 'fileSize', title: '大小' },
  { key: 'chunkCount', title: '分块数' },
  { key: 'parseStatus', title: '状态' },
  { key: 'createdTime', title: '创建时间' },
  { key: 'op', title: '操作' }
]

const kbStats = computed(() => {
  const total = kbs.value.length
  const active = kbs.value.filter(k => k.status === 1).length
  const docs_total = kbs.value.reduce((s, k) => s + (k.docCount || 0), 0)
  const chunks_total = kbs.value.reduce((s, k) => s + (k.chunkCount || 0), 0)
  return { total, active, docs: docs_total, chunks: chunks_total }
})
const canMutateDocs = computed(() => (
  kbsAvailable.value === true && docsAvailable.value === true && Boolean(detailKb.value)
))
const kbsRefreshing = computed(() => kbsLoading.value && kbsAvailable.value === true)
const docsRefreshing = computed(() => docsLoading.value && docsAvailable.value === true)

function kbMetric(value) {
  return kbsAvailable.value === true ? value : '—'
}

const kbModal = reactive({
  visible: false,
  isEdit: false,
  submitting: false,
  form: createEmptyKbForm()
})

const uploadForm = reactive({ fileName: '', content: '' })

const chunksModal = reactive({ visible: false, list: [] })

const searchModal = reactive({
  visible: false,
  kbName: '',
  kbId: null,
  query: '',
  hits: [],
  loading: false,
  searched: false
})

function createEmptyKbForm() {
  return {
    id: null,
    name: '',
    description: '',
    embeddingModel: '',
    embeddingBaseUrl: '',
    embeddingApiKey: '',
    embeddingApiKeyConfigured: false,
    status: 1
  }
}

function formatDateTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').replace(/\.\d+$/, '').slice(0, 19)
}

function formatSize(bytes) {
  const n = Number(bytes) || 0
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(2) + ' MB'
}

function parseStatusType(s) {
  return ({ ready: 'green', pending: 'orange', failed: 'red', skipped: 'blue' })[s] || 'blue'
}

function parseStatusText(status) {
  return ({ ready: '已索引', pending: '待处理', parsing: '解析中', failed: '失败', skipped: '已跳过' })[status] || status || '-'
}

function documentErrorMessage(row) {
  const status = String(row?.parseStatus || '').toLowerCase()
  if (!['failed', 'skipped'].includes(status)) return ''
  return String(row?.errorMessage || row?.error_message || '未生成可检索分块，请检查文档内容与 Embedding 配置')
}

function canReindex(row) {
  return Number(row?.chunkCount || 0) > 0
}

function validateDocumentFile(file) {
  if (!file) return '请先选择文件'
  const name = String(file.name || '').toLowerCase()
  if (!ALLOWED_DOCUMENT_EXTENSIONS.some(ext => name.endsWith(ext))) return '仅支持 .txt 或 .md 文档'
  if (Number(file.size || 0) > MAX_DOCUMENT_BYTES) return '文档不能超过 10MB'
  return ''
}

function applyDocumentUploadResult(response, successMessage) {
  const doc = response?.data || {}
  const status = String(doc.parseStatus || doc.parse_status || '').toLowerCase()
  const chunkCount = Number(doc.chunkCount ?? doc.chunk_count ?? 0)
  const failureMessage = doc.errorMessage || doc.error_message
  if (['failed', 'skipped'].includes(status) || chunkCount <= 0) {
    error.value = failureMessage || '文档已保存，但未生成可检索分块，请检查内容与 Embedding 配置'
    return false
  }
  success.value = successMessage
  setTimeout(() => { success.value = '' }, 2500)
  return true
}
async function loadKbs() {
  const request = kbsRequestGuard.begin()
  const hadSnapshot = kbsAvailable.value === true
  kbsLoading.value = true
  kbsWarning.value = ''
  try {
    const res = await listKnowledgeBases(undefined, listRefreshRequestConfig(hadSnapshot))
    if (!request.isCurrent()) return
    kbs.value = recordsOf(res.data) || []
    kbsAvailable.value = true
    if (detailKb.value) {
      const currentDetail = kbs.value.find(item => String(item.id) === String(detailKb.value.id))
      if (currentDetail) detailKb.value = currentDetail
      else closeDetail()
    }
  } catch (e) {
    if (!request.isCurrent()) return
    if (hadSnapshot) {
      kbsWarning.value = `知识库刷新失败，继续显示上次成功加载的知识库数据。${e.message ? ` ${e.message}` : ''}`
    } else {
      error.value = e.message || '加载失败'
      kbs.value = []
      kbsAvailable.value = false
      if (detailKb.value) closeDetail()
    }
  } finally {
    if (request.isCurrent()) kbsLoading.value = false
  }
}

function refreshKbs() {
  error.value = ''
  success.value = ''
  kbsWarning.value = ''
  loadKbs()
}

function openCreateKb() {
  if (kbsAvailable.value !== true) return
  kbModal.isEdit = false
  kbModal.form = createEmptyKbForm()
  kbModal.visible = true
}

function openEditKb(row) {
  if (kbsAvailable.value !== true) return
  kbModal.isEdit = true
  kbModal.form = {
    id: row.id,
    name: row.name || '',
    description: row.description || '',
    embeddingModel: row.embeddingModel || '',
    embeddingBaseUrl: row.embeddingBaseUrl || '',
    embeddingApiKey: row.embeddingApiKey || '',
    embeddingApiKeyConfigured: Boolean(row.embeddingApiKeyConfigured || row.embeddingApiKey),
    status: row.status != null ? row.status : 1
  }
  kbModal.visible = true
}

function closeKbModal() { kbModal.visible = false }

async function submitKb() {
  if (kbsAvailable.value !== true) {
    error.value = '知识库状态未知，重新加载成功前禁止保存。'
    return
  }
  if (!kbModal.form.name) {
    error.value = '名称不能为空'
    setTimeout(() => { if (error.value) error.value = '' }, 3000)
    return
  }
  kbModal.submitting = true
  error.value = ''
  try {
    const payload = {
      name: kbModal.form.name,
      description: kbModal.form.description || null,
      embeddingModel: kbModal.form.embeddingModel || null,
      embeddingBaseUrl: kbModal.form.embeddingBaseUrl || null,
      embeddingApiKey: kbModal.form.embeddingApiKey || null,
      status: kbModal.form.status != null ? kbModal.form.status : 1
    }
    if (kbModal.isEdit && kbModal.form.id) {
      await updateKnowledgeBase(kbModal.form.id, payload)
      success.value = '已保存'
    } else {
      await createKnowledgeBase(payload)
      success.value = '已创建'
    }
    setTimeout(() => { success.value = '' }, 2500)
    kbModal.visible = false
    await loadKbs()
  } catch (e) {
    error.value = e.message || '提交失败'
  } finally {
    kbModal.submitting = false
  }
}

async function removeKb(row) {
  if (kbsAvailable.value !== true) return
  const confirmed = await confirmAction({
    title: `确认删除知识库“${row.name || row.id}”？`,
    description: '该知识库的所有文档和分块将被一并删除，此操作不可撤销。',
    dangerous: true,
  })
  if (!confirmed) return
  error.value = ''
  try {
    await deleteKnowledgeBase(row.id)
    success.value = '已删除'
    setTimeout(() => { success.value = '' }, 2000)
    await loadKbs()
  } catch (e) {
    error.value = e.message || '删除失败'
  }
}

async function openKbDetail(row) {
  if (kbsAvailable.value !== true) return
  docsRequestGuard.invalidate()
  docsLoading.value = false
  detailKb.value = row
  docs.value = []
  docsAvailable.value = null
  docsError.value = ''
  docsWarning.value = ''
  uploadForm.fileName = ''
  uploadForm.content = ''
  pickedFile.value = null
  await loadDocs()
}

function closeDetail() {
  docsRequestGuard.invalidate()
  docsLoading.value = false
  detailKb.value = null
  docs.value = []
  docsAvailable.value = null
  docsError.value = ''
  docsWarning.value = ''
}

async function loadDocs() {
  if (!detailKb.value) return
  const request = docsRequestGuard.begin()
  const hadSnapshot = docsAvailable.value === true
  const kbId = detailKb.value.id
  docsLoading.value = true
  docsError.value = ''
  docsWarning.value = ''
  try {
    const res = await listDocuments(kbId, undefined, listRefreshRequestConfig(hadSnapshot))
    if (!request.isCurrent()) return
    docs.value = recordsOf(res.data) || []
    docsAvailable.value = true
  } catch (e) {
    if (!request.isCurrent()) return
    if (hadSnapshot) {
      docsWarning.value = `文档列表刷新失败，继续显示上次成功加载的文档数据。${e.message ? ` ${e.message}` : ''}`
    } else {
      docsError.value = e.message || '文档加载失败'
      docs.value = []
      docsAvailable.value = false
    }
  } finally {
    if (request.isCurrent()) docsLoading.value = false
  }
}

function onFilePick(e) {
  if (!canMutateDocs.value) return
  const f = e.target.files && e.target.files[0]
  const validationError = validateDocumentFile(f)
  if (validationError) {
    pickedFile.value = null
    error.value = validationError
    if (e.target) e.target.value = ''
    return
  }
  error.value = ''
  pickedFile.value = f
}

async function uploadManual() {
  if (!canMutateDocs.value) return
  if (!uploadForm.content) {
    error.value = '请输入文本内容'
    setTimeout(() => { if (error.value) error.value = '' }, 3000)
    return
  }
  const manualName = String(uploadForm.fileName || '').trim()
  if (manualName && !ALLOWED_DOCUMENT_EXTENSIONS.some(ext => manualName.toLowerCase().endsWith(ext))) {
    error.value = '手动文本文件名必须使用 .txt 或 .md 扩展名'
    return
  }
  if (new TextEncoder().encode(uploadForm.content).byteLength > MAX_DOCUMENT_BYTES) {
    error.value = '文本内容不能超过 10MB'
    return
  }
  uploading.value = true
  error.value = ''
  try {
    const response = await uploadDocument(detailKb.value.id, {
      content: uploadForm.content,
      fileName: uploadForm.fileName || ('manual-' + Date.now() + '.txt')
    })
    applyDocumentUploadResult(response, '已上传并索引')
    uploadForm.content = ''
    uploadForm.fileName = ''
    await loadDocs()
    await loadKbs()
  } catch (e) {
    error.value = e.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

async function uploadFile() {
  if (!canMutateDocs.value) return
  if (!pickedFile.value) {
    error.value = '请先选择文件'
    setTimeout(() => { if (error.value) error.value = '' }, 3000)
    return
  }
  const validationError = validateDocumentFile(pickedFile.value)
  if (validationError) {
    error.value = validationError
    return
  }
  uploading.value = true
  error.value = ''
  try {
    const fd = new FormData()
    fd.append('file', pickedFile.value)
    const response = await uploadDocument(detailKb.value.id, fd)
    applyDocumentUploadResult(response, '已上传并索引')
    pickedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await loadDocs()
    await loadKbs()
  } catch (e) {
    error.value = e.message || '上传失败'
  } finally {
    uploading.value = false
  }
}
async function removeDoc(row) {
  if (!canMutateDocs.value) return
  const confirmed = await confirmAction({
    title: `确认删除文档“${row.fileName || row.id}”？`,
    description: '文档及其向量分块将被删除，此操作不可撤销。',
    dangerous: true,
  })
  if (!confirmed) return
  error.value = ''
  try {
    await deleteDocument(detailKb.value.id, row.id)
    success.value = '已删除'
    setTimeout(() => { success.value = '' }, 2000)
    await loadDocs()
    await loadKbs()
  } catch (e) {
    error.value = e.message || '删除失败'
  }
}

async function reindexDoc(row) {
  if (!canMutateDocs.value || !canReindex(row) || reindexing.value === row.id) return
  reindexing.value = row.id
  error.value = ''
  try {
    await reindexDocument(detailKb.value.id, row.id)
    success.value = '已重新索引'
    setTimeout(() => { success.value = '' }, 2500)
    await loadDocs()
    await loadKbs()
  } catch (e) {
    error.value = e.message || '重建索引失败'
  } finally {
    reindexing.value = null
  }
}

async function viewChunks(row) {
  if (!canMutateDocs.value) return
  error.value = ''
  try {
    const res = await listChunks(detailKb.value.id, row.id)
    chunksModal.list = recordsOf(res.data) || []
    chunksModal.visible = true
  } catch (e) {
    error.value = e.message || '加载分块失败'
  }
}

function openSearchKb(row) {
  if (kbsAvailable.value !== true) return
  searchModal.kbId = row.id
  searchModal.kbName = row.name
  searchModal.query = ''
  searchModal.hits = []
  searchModal.searched = false
  searchAvailable.value = null
  searchModal.visible = true
}

async function runSearch() {
  if (!searchModal.kbId) return
  if (!searchModal.query) {
    error.value = '请输入查询文本'
    setTimeout(() => { if (error.value) error.value = '' }, 3000)
    return
  }
  searchModal.loading = true
  searchAvailable.value = null
  error.value = ''
  try {
    const res = await searchKnowledge(searchModal.kbId, {
      query: searchModal.query,
      topK: 5,
      similarityThreshold: 0.3
    })
    searchModal.hits = recordsOf(res.data) || []
    searchModal.searched = true
    searchAvailable.value = true
  } catch (e) {
    error.value = e.message || '检索失败'
    searchModal.hits = []
    searchModal.searched = false
    searchAvailable.value = false
  } finally {
    searchModal.loading = false
  }
}

onMounted(() => {
  loadKbs()
})

onBeforeUnmount(() => {
  kbsRequestGuard.invalidate()
  docsRequestGuard.invalidate()
})
</script>

<style scoped>
.admin-rag { display: flex; flex-direction: column; gap: 16px; }
.warning { background: #fff8e8; color: #8a4b08; border-color: #f7c97a; }
.refresh-status { margin-bottom: 10px; color: #526079; font-size: 13px; }
.stat-grid { display: grid; gap: 12px; }
.toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; padding: 6px 4px; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row-full { grid-column: 1 / -1; }
.form-row label { font-size: 13px; color: #526079; font-weight: 600; }
.form-row label em { color: #ef4444; font-style: normal; margin-left: 2px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.subtle { color: #758198; font-size: 13px; margin: 4px 0 12px; }
.detail-toolbar { display: flex; flex-direction: column; gap: 8px; padding: 12px; background: #f6f9ff; border: 1px solid #e4ebf5; border-radius: 12px; }
.detail-toolbar-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.upload-hint { color: #667085; line-height: 1.6; }
.parse-status-cell { display: grid; gap: 4px; max-width: 240px; }
.parse-status-cell small { color: #b42318; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chunks-list { max-height: 420px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.chunk-item { background: #f6f9ff; border: 1px solid #e4ebf5; border-radius: 10px; padding: 10px 12px; }
.chunk-head { display: flex; justify-content: space-between; margin-bottom: 6px; color: #526079; font-size: 12px; }
.chunk-item pre { white-space: pre-wrap; word-break: break-word; margin: 0; font-family: inherit; font-size: 13px; color: #2d3448; }
.search-box { display: flex; gap: 8px; margin-bottom: 14px; }
.search-hits { max-height: 360px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.hit-item { background: #f6f9ff; border: 1px solid #e4ebf5; border-radius: 10px; padding: 10px 12px; }
.hit-head { display: flex; justify-content: space-between; margin-bottom: 6px; color: #526079; font-size: 12px; }
.hit-item pre { white-space: pre-wrap; word-break: break-word; margin: 0; font-family: inherit; font-size: 13px; color: #2d3448; }

/* ===== 移动端响应式（max-width: 900px）===== */
@media (max-width: 900px) {
  .admin-rag { gap: 12px; }

  .stat-grid {
    grid-template-columns: minmax(0, 1fr) !important;
    gap: 10px;
  }

  .toolbar {
    gap: 8px;
  }

  /* 模态框：覆盖 inline 宽度，改为底部全宽弹出 */
  .xy-modal {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    border-radius: 14px 14px 0 0 !important;
    max-height: 90vh;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }

  .modal-mask {
    align-items: flex-end !important;
    padding: 0 !important;
  }

  .modal-mask .xy-modal {
    width: 100% !important;
  }

  .modal-actions {
    gap: 8px;
    margin-top: 14px;
  }

  .subtle {
    font-size: 12px;
    margin: 4px 0 10px;
  }

  /* 表单网格 → 单列堆叠 */
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
    padding: 4px 2px;
  }

  .stat-grid > *,
  .form-grid > * {
    min-width: 0;
  }

  .form-row-full {
    grid-column: 1 / -1;
  }

  .form-row label {
    font-size: 12.5px;
  }

  /* 知识库详情/上传工具区 */
  .detail-toolbar {
    padding: 10px;
    gap: 8px;
    border-radius: 10px;
  }

  .detail-toolbar-row {
    gap: 6px;
  }

  /* 分块列表 / 检索结果区域：允许横向滚动 + 限高 */
  .chunks-list {
    max-height: 56vh;
    overflow: auto;
    -webkit-overflow-scrolling: touch;
    gap: 8px;
  }

  .chunk-item {
    padding: 10px;
    border-radius: 8px;
  }

  .chunk-head {
    font-size: 11.5px;
    margin-bottom: 4px;
  }

  .chunk-item pre {
    font-size: 12.5px;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .search-box {
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
  }

  .search-box .input {
    flex: 1 1 100%;
  }

  .search-hits {
    max-height: 50vh;
    overflow: auto;
    -webkit-overflow-scrolling: touch;
    gap: 8px;
  }

  .hit-item {
    padding: 10px;
    border-radius: 8px;
  }

  .hit-head {
    font-size: 11.5px;
    margin-bottom: 4px;
    flex-wrap: wrap;
    gap: 4px;
  }

  .hit-item pre {
    font-size: 12.5px;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* 让宽表格横向滚动，避免撑破容器 */
  :deep(.base-table),
  :deep(.base-table-wrap),
  :deep(table) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    max-width: 100%;
  }
}
</style>
