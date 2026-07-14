<template>
  <div>
    <div class="toolbar"><span class="subtle">统计范围：</span><b>全部账号</b><span class="subtle">更新时间：{{ updatedAt }}</span><label class="subtle" for="stats-date" style="margin-left:auto">统计日期：</label><input id="stats-date" v-model="date" class="input" type="date" aria-label="统计日期" style="max-width:180px" :disabled="loading" @change="load"><AppButton :disabled="loading" @click="load">{{ loading ? '加载中...' : '刷新' }}</AppButton></div>
    <div v-if="error" class="global-notice error">{{ error }}</div>
    <div class="grid stat-grid">
      <StatCard title="订单数" :value="metricValue(stats.orderCount)" change="订单统计" icon="product" />
      <StatCard title="发货成功" :value="metricValue(stats.deliverySuccessCount)" change="成功发货记录" icon="record" color="green" />
      <StatCard title="发货失败" :value="metricValue(stats.deliveryFailCount)" change="失败发货记录" icon="task" color="orange" />
      <StatCard title="待发货" :value="metricValue(stats.pendingDeliveryCount)" change="待处理发货记录" icon="task" color="purple" />
      <StatCard title="AI回复" :value="metricValue(stats.aiReplyCount)" change="自动回复记录" icon="chat" />
      <StatCard title="数据状态" :value="loading ? '加载中' : (dataAvailable ? (stats.hasData ? '有数据' : '暂无数据') : '不可用')" change="后端统计结果" icon="data" :color="dataAvailable ? 'green' : 'orange'" />
    </div>
    <div class="grid three-col">
      <CardPanel title="发货成功趋势"><template #action><div class="chips"><span class="chip">近7天</span></div></template><EmptyState v-if="!trendAvailable" icon="📊" title="趋势暂不可用" description="汇总与趋势独立加载，可点击刷新重试。" /><MiniLineChart v-else :values="trend.deliverySuccess" :labels="trend.dates" /></CardPanel>
      <CardPanel title="发货失败趋势"><EmptyState v-if="!trendAvailable" icon="📊" title="趋势暂不可用" description="汇总与趋势独立加载，可点击刷新重试。" /><MiniLineChart v-else :values="trend.deliveryFail" :labels="trend.dates" /></CardPanel>
      <CardPanel title="AI 回复概况"><EmptyState v-if="!dataAvailable" icon="📊" title="统计暂不可用" description="当前不会以全零数据代替查询失败。" /><DonutChart v-else :center="String(totalReplies)" label="AI回复" :items="replyItems" /></CardPanel>
    </div>
    <div class="grid three-col" style="margin-top:16px">
      <CardPanel title="趋势明细">
        <EmptyState v-if="!trendAvailable" icon="📋" title="明细暂不可用" description="趋势查询恢复后再显示。" />
        <BaseTable v-else :columns="trendCols" :rows="trendRows" />
      </CardPanel>
      <CardPanel title="发货概况">
        <EmptyState v-if="!dataAvailable" icon="📦" title="发货统计暂不可用" description="不会把查询失败显示为零。" />
        <template v-else>
          <DonutChart :center="String(totalDelivery)" label="发货合计" :items="deliveryItems" />
          <div class="metric-row" style="margin-top:20px"><div class="metric-tile"><span>成功率</span><b style="color:var(--green)">{{ successRate }}</b></div><div class="metric-tile"><span>失败</span><b style="color:#ef4444">{{ stats.deliveryFailCount }}</b></div><div class="metric-tile"><span>待处理</span><b>{{ stats.pendingDeliveryCount }}</b></div></div>
        </template>
      </CardPanel>
      <CardPanel title="最新实时事件">
        <EmptyState v-if="logs.length === 0" icon="📡" title="暂无实时事件" description="订单、发货、AI 回复等实时事件会在这里显示。" />
        <div v-for="n in logs" :key="n.t+n.time" class="option-line"><div><b>{{ n.t }}</b><p class="subtle" style="margin:4px 0 0">{{ n.d }}</p></div><span class="subtle">{{ n.time }}</span></div>
      </CardPanel>
    </div>
    <CardPanel title="快捷操作" style="margin-top:16px"><div class="grid quick-grid"><button v-for="q in quick" :key="q.key" type="button" class="quick-card" @click="$emit('navigate', q.key)"><span class="circle-ico blue-bg" aria-hidden="true">＋</span><span><b>{{ q.label }}</b><span>快速进入常用功能</span></span></button></div></CardPanel>
  </div>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import StatCard from '../components/StatCard.vue'; import CardPanel from '../components/CardPanel.vue'; import MiniLineChart from '../components/MiniLineChart.vue'; import DonutChart from '../components/DonutChart.vue'; import BaseTable from '../components/BaseTable.vue'; import AppButton from '../components/AppButton.vue'; import EmptyState from '../components/EmptyState.vue'
import { getDashboardSummary, getDashboardSalesTrend } from '../api/dashboard.js'
import { shortText } from '../utils/format.js'
defineEmits(['navigate'])
const stats = ref({ orderCount:0, deliverySuccessCount:0, deliveryFailCount:0, pendingDeliveryCount:0, aiReplyCount:0, hasData:false })
const trend = ref({ dates:[], deliverySuccess:[], deliveryFail:[], aiReplies:[] })
const updatedAt = ref('-')
const error = ref('')
const loading = ref(false)
const dataAvailable = ref(false)
const trendAvailable = ref(false)
const loadedSummaryDate = ref(null)
const loadedTrendDate = ref(null)
const logs = ref([])
const date = ref('')
const totalDelivery = computed(() => Number(stats.value.deliverySuccessCount || 0) + Number(stats.value.deliveryFailCount || 0))
const totalReplies = computed(() => Number(stats.value.aiReplyCount || 0))
const successRate = computed(() => totalDelivery.value ? `${Math.round(Number(stats.value.deliverySuccessCount || 0) * 100 / totalDelivery.value)}%` : '—')
const deliveryItems = computed(() => [{label:'成功', value:String(stats.value.deliverySuccessCount || 0)}, {label:'失败', value:String(stats.value.deliveryFailCount || 0)}, {label:'待发货', value:String(stats.value.pendingDeliveryCount || 0)}])
const replyItems = computed(() => [{label:'AI回复', value:String(totalReplies.value)}])
const trendCols=[{key:'date',title:'日期'},{key:'success',title:'发货成功'},{key:'fail',title:'发货失败'},{key:'reply',title:'AI回复'}]
const trendRows = computed(() => (trend.value.dates || []).map((d,i)=>({date:d, success:trend.value.deliverySuccess?.[i] || 0, fail:trend.value.deliveryFail?.[i] || 0, reply:trend.value.aiReplies?.[i] || 0})))
const quick=[{label:'添加闲鱼账号',key:'accounts'},{label:'发布新商品',key:'product-publish'},{label:'同步商品',key:'products'},{label:'配置自动发货',key:'auto-delivery'},{label:'广告申请',key:'ad-application'},{label:'卡密管理',key:'card-warehouse'},{label:'反馈建议',key:'feedback'},{label:'更多功能',key:'settings-system'}]
function metricValue(value) { return dataAvailable.value ? value : '—' }
async function load(){
  if (loading.value) return
  const requestDate = date.value || ''
  const hadSummarySnapshot = dataAvailable.value && loadedSummaryDate.value === requestDate
  const hadTrendSnapshot = trendAvailable.value && loadedTrendDate.value === requestDate
  if (!hadSummarySnapshot) dataAvailable.value = false
  if (!hadTrendSnapshot) trendAvailable.value = false
  loading.value = true
  error.value = ''
  try {
    const rangeParams = requestDate ? { date: requestDate } : {}
    const [summaryResult, trendResult] = await Promise.allSettled([
      getDashboardSummary(rangeParams),
      getDashboardSalesTrend(rangeParams)
    ])
    const failures = []
    const summarySucceeded = summaryResult.status === 'fulfilled' && Boolean(summaryResult.value?.data)
    const trendSucceeded = trendResult.status === 'fulfilled' && Boolean(trendResult.value?.data)
    if (summarySucceeded) {
      const sd = summaryResult.value.data
      stats.value = {
        orderCount: sd.todayOrderCount ?? sd.orderCount ?? 0,
        deliverySuccessCount: sd.deliverySuccessCount ?? 0,
        deliveryFailCount: sd.deliveryFailCount ?? 0,
        pendingDeliveryCount: sd.pendingDeliveryCount ?? 0,
        aiReplyCount: sd.autoReplyCount ?? sd.aiReplyCount ?? 0,
        hasData: !!(
          (sd.todayOrderCount ?? sd.orderCount) || sd.deliverySuccessCount ||
          sd.deliveryFailCount || sd.pendingDeliveryCount ||
          (sd.autoReplyCount ?? sd.aiReplyCount)
        )
      }
      dataAvailable.value = true
      loadedSummaryDate.value = requestDate
    } else {
      dataAvailable.value = hadSummarySnapshot
      failures.push('运营汇总')
    }
    if (trendSucceeded) {
      const td = trendResult.value.data
      trend.value = {
        dates: td.dates || [],
        deliverySuccess: td.deliverySuccess || [],
        deliveryFail: td.deliveryFail || [],
        aiReplies: td.aiReplyCount || td.aiReplies || []
      }
      trendAvailable.value = true
      loadedTrendDate.value = requestDate
    } else {
      trendAvailable.value = hadTrendSnapshot
      failures.push('趋势')
    }
    const refreshed = summarySucceeded || trendSucceeded
    if (refreshed) updatedAt.value = new Date().toLocaleString('zh-CN', { hour12:false })
    else if (!hadSummarySnapshot && !hadTrendSnapshot) updatedAt.value = '不可用'
    if (failures.length) {
      const preserved = hadSummarySnapshot || hadTrendSnapshot ? '；同一日期的上次成功数据已保留' : ''
      error.value = `${failures.join('、')}暂不可用${preserved}；失败区域不会以全零数据代替。`
    }
  } catch {
    dataAvailable.value = hadSummarySnapshot
    trendAvailable.value = hadTrendSnapshot
    if (!hadSummarySnapshot && !hadTrendSnapshot) updatedAt.value = '不可用'
    error.value = hadSummarySnapshot || hadTrendSnapshot
      ? '统计服务暂不可用，已保留同一日期的上次成功数据。请检查服务状态后重试。'
      : '统计服务暂不可用，当前不会用全零数据代替查询失败。请检查服务状态后重试。'
  } finally {
    loading.value = false
  }
}
function onSse(event){ const d=event.detail||{}; logs.value.unshift({t:d.type||d.event||'实时事件', d:shortText(d.message||d.content||'状态已更新',70), time:new Date().toLocaleTimeString('zh-CN',{hour12:false})}); logs.value=logs.value.slice(0,5) }
function onHeader(e){ if(e.detail === 'refresh-data-panel') load() }
onMounted(()=>{ window.addEventListener('xya-sse-event', onSse); window.addEventListener('xya-header-action', onHeader); load() })
onBeforeUnmount(()=>{ window.removeEventListener('xya-sse-event', onSse); window.removeEventListener('xya-header-action', onHeader) })
</script>
<style scoped>
/* ===== 移动端响应式 (max-width: 900px) ===== */
@media (max-width: 900px) {
  /* 事件列表项：允许换行，时间另起一行 */
  .option-line {
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px 0;
  }

  .option-line > div {
    flex: 1 1 100%;
    min-width: 0;
  }

  .option-line > span {
    font-size: 11px;
  }

  /* chips 标签收敛 */
  .chip {
    font-size: 11px;
  }
}
</style>
