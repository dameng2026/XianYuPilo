<template>
  <div class="products-page">
    <div class="products-main">
      <div v-if="notice.text" :class="['global-notice', notice.type]">{{ notice.text }}</div>
      
      <!-- 自动同步状态横幅 -->
      <div v-if="autoSyncState.active" class="global-notice info">
        <strong>正在同步闲鱼商品...</strong>
        <template v-if="autoSyncState.accountTotal > 1">
          <span>（账号 {{ autoSyncState.accountIndex }}/{{ autoSyncState.accountTotal }}：{{ autoSyncState.accountLabel }}）</span>
        </template>
        <span v-if="autoSyncState.progress > 0">进度 {{ autoSyncState.progress }}%</span>
        <span class="muted" style="margin-left:8px">请勿离开当前页面，同步完成后将自动展示最新商品</span>
      </div>
      <div v-else-if="autoSyncState.partial" class="global-notice warn">
        <strong>闲鱼商品同步部分完成：</strong>
        <span>成功 {{ autoSyncState.accountTotal - autoSyncState.failedAccounts.length }} / 失败 {{ autoSyncState.failedAccounts.length }}</span>
        <span class="muted">失败账号：{{ autoSyncState.failedAccounts.map(item => item.label).join('、') }}</span>
        <button class="link" @click="syncProducts">重新同步全部账号</button>
      </div>
      <div v-else-if="autoSyncState.completed" class="global-notice success">
        <strong>闲鱼商品同步完成！</strong>
        <span style="margin-left:8px">
          共同步 <b>{{ autoSyncState.summary.total }}</b> 件商品，
          新增 <b>{{ autoSyncState.summary.new }}</b>，
          更新 <b>{{ autoSyncState.summary.updated }}</b>
          <template v-if="autoSyncState.summary.offShelf">
            ，下架 <b>{{ autoSyncState.summary.offShelf }}</b>
          </template>
          ，耗时 {{ autoSyncState.summary.duration }}秒
        </span>
        <span v-if="autoSyncState.accountTotal > 1" class="muted" style="margin-left:8px">| 共同步 {{ autoSyncState.accountTotal }} 个账号</span>
        <span class="muted" style="margin-left:8px">| 当前展示同步后的最新商品数据</span>
        <button class="link" style="margin-left:8px" @click="showAllProducts">查看全部商品</button>
      </div>
      <div v-else-if="autoSyncState.error" class="global-notice error">
        <strong>自动同步失败：</strong>{{ autoSyncState.error }}
        <button class="link" style="margin-left:8px" @click="syncProducts">重试同步</button>
      </div>

      <div v-if="currentAccountPolishTask" :class="['global-notice', polishNoticeType(currentAccountPolishTask.status), 'polish-progress-banner']" role="status">
        <div>
          <strong>{{ polishScopeButtonText(query.xianyuAccountId, [], '擦亮当前账号') }}</strong>
          <span>{{ currentAccountPolishTask.message }}</span>
          <span>
            进度 {{ currentAccountPolishTask.processed }}/{{ currentAccountPolishTask.total }}，
            已确认 {{ currentAccountPolishTask.polished }}，今日已擦亮 {{ currentAccountPolishTask.alreadyDone }}，
            明确失败 {{ currentAccountPolishTask.failed }}<template v-if="currentAccountPolishTask.unknown">，未知 {{ currentAccountPolishTask.unknown }}</template>
          </span>
          <small v-if="currentAccountPolishPollMessage">{{ currentAccountPolishPollMessage }}</small>
          <small v-if="itemPolishRetryGuidance(currentAccountPolishTask)">{{ itemPolishRetryGuidance(currentAccountPolishTask) }}</small>
        </div>
        <button v-if="itemPolishCanResume(currentAccountPolishTask) && !isPolishScopeBusy(query.xianyuAccountId)" class="link" :aria-busy="isPolishScopeActionLoading(query.xianyuAccountId)" @click="polishCurrentAccount">{{ currentAccountPolishTask.status === 'needs_verification' ? '我已完成验证，继续原任务' : (['partial', 'failed'].includes(currentAccountPolishTask.status) ? '复用原任务处理明确未擦亮项' : '继续安全任务') }}</button>
        <span v-else-if="currentAccountPolishTask.status === 'unknown'" class="muted">请先在闲鱼 App 逐项核对，系统不会自动重试。</span>
        <span v-else-if="currentAccountPolishTask.status === 'needs_verification'" class="muted">请先在闲鱼 App 完成安全验证，系统不会自动重试。</span>
      </div>
      <ItemPolishUnknownReconcile
        v-if="currentAccountPolishTask"
        :task="currentAccountPolishTask"
        :busy-goods-id="currentAccountPolishReconcileBusyGoodsId"
        :error-message="currentAccountPolishReconcileMessage"
        @reconcile="reconcileCurrentAccountPolishTask"
      />
      <ItemPolishConflictCard
        v-if="activePolishConflict"
        :conflict="activePolishConflict"
        :refreshing="activePolishConflictRefreshing"
        :refresh-message="activePolishConflictRefreshMessage"
        @refresh="refreshActivePolishConflict"
      />

      <div class="grid stat-grid products-stat-grid">
        <StatCard title="商品总数" :value="statsAvailable === true ? goodsStats.total : '—'" :change="statsAvailable === false ? '统计暂不可用' : '全部商品'" icon="record" color="green" />
        <StatCard title="在售商品" :value="statsAvailable === true ? goodsStats.onSale : '—'" :change="statsAvailable === false ? '统计暂不可用' : '正在售卖'" icon="data" color="green" />
        <StatCard title="下架/草稿" :value="statsAvailable === true ? goodsStats.offShelfOrDraft : '—'" :change="statsAvailable === false ? '统计暂不可用' : '未上架'" icon="data" color="orange" />
        <StatCard title="自动发货" :value="statsAvailable === true ? goodsStats.autoDeliveryOn : '—'" :change="statsAvailable === false ? '统计暂不可用' : '已开启商品数'" icon="truck" color="purple" />
        <StatCard title="自动回复" :value="statsAvailable === true ? goodsStats.autoReplyAccounts : '—'" :change="statsAvailable === false ? '统计暂不可用' : '已开启账号数'" icon="chat" />
        <StatCard title="当前账号" :value="selectedAccountName" change="可切换账号" icon="shield" color="gray" />
      </div>
      <CardPanel class="products-table-card">
        <div class="products-toolbar">
          <div class="toolbar-filter">
            <div class="filter-left">
              <select v-model="query.xianyuAccountId" class="input toolbar-select" @change="onAccountChange">
                <option :value="''">全部账号</option>
                <option v-for="a in accounts" :key="a.id" :value="a.id">{{ accountName(a) }}</option>
              </select>
              <div class="tabs products-tabs">
                <button :class="['tab',{active:query.status === ''}]" @click="setStatus('')">全部</button>
                <button :class="['tab',{active:query.status === 0}]" @click="setStatus(0)">在售</button>
                <button :class="['tab',{active:query.status === 1}]" @click="setStatus(1)">下架/草稿</button>
                <button :class="['tab',{active:query.status === 3}]" @click="setStatus(3)">已删除</button>
              </div>
            </div>
            <div class="filter-search">
              <input v-model="query.keyword" class="input products-search-input" placeholder="搜索 商品标题 / 商品ID" @keyup.enter="loadItems">
              <AppButton :loading="loading" @click="loadItems">搜索</AppButton>
              <AppButton :disabled="loading" @click="resetQuery">重置</AppButton>
            </div>
          </div>
          <div class="toolbar-actions">
            <AppButton
              type="warn"
              :disabled="listAvailable !== true || !query.xianyuAccountId || isPolishScopeBusy(query.xianyuAccountId)"
              :loading="isPolishScopeActionLoading(query.xianyuAccountId)"
              :loading-text="polishScopeButtonText(query.xianyuAccountId, [], '擦亮当前账号')"
              :title="itemPolishRetryGuidance(currentAccountPolishTask) || currentAccountPolishTask?.message || '擦亮当前账号在售商品'"
              @click="polishCurrentAccount"
            >
              {{ polishScopeButtonText(query.xianyuAccountId, [], '擦亮当前账号') }}
            </AppButton>
            <AppButton type="danger" :disabled="listAvailable !== true || selectedKeys.length === 0 || batchDeleting" @click="batchDeleteProducts">
              {{ batchDeleteBtnText }}
            </AppButton>
            <AppButton type="primary" :disabled="listAvailable === false || syncing || autoSyncState.active" @click="syncProducts">{{ syncing || autoSyncState.active ? (autoSyncState.accountTotal > 1 ? `同步中 ${autoSyncState.accountIndex}/${autoSyncState.accountTotal}...` : '同步中...') : '同步闲鱼商品' }}</AppButton>
          </div>
        </div>
        <div v-if="batchDeleteState.active" class="global-notice warn">
          <strong>正在批量删除商品...</strong>
          <span>{{ batchDeleteState.done }}/{{ batchDeleteState.total }}</span>
          <span v-if="batchDeleteState.current" class="muted" style="margin-left:8px">{{ batchDeleteState.current }}</span>
        </div>
        <div v-else-if="batchDeleteState.result" class="global-notice" :class="batchDeleteState.result.failed.length ? 'warn' : 'success'">
          <strong>批量删除完成：</strong>
          <span>成功 <b>{{ batchDeleteState.result.success }}</b> / 失败 <b>{{ batchDeleteState.result.failed.length }}</b></span>
          <button v-if="batchDeleteState.result.failed.length" class="link" style="margin-left:8px" :title="batchDeleteState.result.failed.map(f => `${f.name}: ${f.reason}`).join('\n')">查看失败详情</button>
          <button v-if="batchDeleteState.result.warnings && batchDeleteState.result.warnings.length" class="link" style="margin-left:8px" :title="batchDeleteState.result.warnings.map(w => `${w.name}: ${w.reason}`).join('\n')">需人工核对({{ batchDeleteState.result.warnings.length }})</button>
          <button class="link" style="margin-left:8px" @click="batchDeleteState.result = null">关闭</button>
        </div>
        <div class="table-scroll-wrap">
          <EmptyState v-if="listAvailable === false" icon="⚠" title="商品列表暂不可用" description="无法确认当前商品状态，所有商品写操作已安全禁用。请恢复服务后重试。">
            <template #actions><AppButton :loading="loading" @click="loadItems">重试加载</AppButton></template>
          </EmptyState>
          <BaseTable
            v-else
            v-model:selected-keys="selectedKeys"
            :columns="cols"
            :rows="products"
            :row-class="rowClass"
            :selectable="true"
            :row-key="rowKeyFn"
            class="products-table"
            @row-click="selectProduct"
          >
            <template #info="{row}"><div class="product-cell"><img v-if="row.coverPic" :src="row.coverPic" class="product-thumb" alt=""><div v-else class="product-thumb product-thumb-placeholder"></div><div class="product-info-text"><strong :title="row.raw?.title || row.name">{{ row.name }}</strong><em>ID：{{ row.xyGoodId }}</em></div></div></template>
            <template #price="{row}"><div class="cell-price">{{ row.price }}</div></template>
            <template #stock="{row}"><div class="cell-center cell-muted">{{ row.stock }}</div></template>
            <template #sku="{row}"><div class="cell-center cell-muted">{{ row.sku }}</div></template>
            <template #status="{row}">
              <div class="cell-center">
                <Badge :type="row.statusType">{{ row.status }}</Badge>
                <small v-if="row.remoteDeleteAttempt" :class="['remote-delete-state', `state-${row.remoteDeleteAttempt.status}`]">
                  {{ remoteDeleteStatusText(row) }}
                </small>
                <small v-if="row.offShelfAttempt && row.offShelfAttempt.status !== 'confirmed'" :class="['remote-delete-state', `state-${row.offShelfAttempt.status}`]">
                  {{ offShelfStatusText(row) }}
                </small>
              </div>
            </template>
            <template #type="{row}">
              <button v-if="row.type === '未配置'" class="delivery-type-configurable" type="button" @click.stop="goToAutoDelivery(row)">
                <Badge type="orange">暂未配置</Badge>
                <span class="config-hint">去配置</span>
              </button>
              <Badge v-else :type="row.type==='卡密'?'purple':row.type==='自定义'?'blue':'green'">{{ row.type }}</Badge>
            </template>
            <template #reply="{row}"><div class="cell-center"><ToggleSwitch :on="row.replyOn" @click.stop="toggleReply(row)" /></div></template>
            <template #onsale="{row}"><div class="cell-center"><AppButton v-if="row.isLocalDraft" type="primary" :disabled="listAvailable !== true" @click.stop="publishDraft(row)">发布</AppButton><ToggleSwitch v-else :on="row.statusCode===0" @click.stop="toggleOnShelf(row)" /></div></template>
            <template #op="{row}">
              <div class="op-buttons">
                <button class="link" @click.stop="selectProduct(row)">详情</button>
                <button v-if="!row.isLocalDraft" class="link" :disabled="listAvailable !== true || isItemBusy(row)" @click.stop="refreshSingle(row)">同步</button>
                <button
                  v-if="!row.isLocalDraft && row.statusCode === 0"
                  class="link"
                  :disabled="listAvailable !== true || productPolishBusy(row)"
                  :aria-busy="productPolishActionLoading(row)"
                  :title="itemPolishRetryGuidance(productPolishTask(row)) || productPolishTask(row)?.message || '执行真实闲鱼擦亮；未知结果不会自动重试'"
                  @click.stop="polishProduct(row)"
                >
                  {{ productPolishButtonText(row) }}
                </button>
                <button v-if="row.isLocalDraft" class="link" :disabled="listAvailable !== true || isItemBusy(row)" @click.stop="publishDraft(row)">{{ isItemBusy(row) ? '处理中' : '发布' }}</button>
                <button class="link danger-text" :disabled="listAvailable !== true || isItemBusy(row) || isRemoteDeleteLocked(row) || isOffShelfBlockingOtherWrites(row)" @click.stop="deleteProduct(row)">
                  {{ remoteDeleteButtonText(row) }}
                </button>
              </div>
            </template>
            <template #empty>
              <EmptyState v-if="autoSyncState.active" icon="⏳" title="正在同步闲鱼商品" :description="`正在从闲鱼获取商品数据... 进度 ${autoSyncState.progress}%`">
                <template #actions><span class="muted">同步完成后将自动展示最新商品</span></template>
              </EmptyState>
              <EmptyState v-else-if="autoSyncState.completed && products.length === 0" icon="🛍" title="本次同步未获取到商品" description="闲鱼账号中可能没有在售商品，或商品数据尚未完全同步。您可以稍后重试。">
                <template #actions><AppButton type="primary" @click="syncProducts">重新同步</AppButton></template>
              </EmptyState>
              <EmptyState v-else icon="🛍" title="还没有商品数据" description="先选择账号并同步闲鱼商品；如果是第一次使用，请先到闲鱼账号页完成账号绑定。">
                <template #actions><AppButton type="primary" :disabled="syncing" @click="syncProducts">{{ syncing ? '同步中...' : '同步闲鱼商品' }}</AppButton><AppButton @click="emit('navigate','accounts')">添加账号</AppButton></template>
              </EmptyState>
            </template>
          </BaseTable>
        </div>
        <div v-if="listAvailable === true" class="pagination products-pagination">
          <div class="pagination-left">
            <span class="page-size-label">每页显示</span>
            <select class="input page-size-select" :value="query.pageSize" @change="onPageSizeChange">
              <option v-for="s in pageSizes" :key="s" :value="s">{{ s }}</option>
            </select>
            <span class="page-size-unit">条</span>
          </div>
          <div class="pagination-right">
            <span class="pagination-total">{{ loading ? '加载中...' : `共 ${totalCount} 条 / ${totalPages} 页` }}</span>
            <button class="page-no" :disabled="query.pageNum <= 1" @click="prevPage">‹</button>
            <template v-for="(p, idx) in pageList" :key="idx">
              <span v-if="p === '...'" class="page-ellipsis">…</span>
              <button v-else :class="['page-no', { active: p === query.pageNum }]" @click="goToPage(p)">{{ p }}</button>
            </template>
            <button class="page-no" :disabled="query.pageNum * query.pageSize >= totalCount" @click="nextPage">›</button>
          </div>
        </div>
      </CardPanel>

      <CardPanel title="同步任务历史" style="margin-top:16px">
        <div class="toolbar compact">
          <select v-model="syncQuery.status" class="input" style="max-width:150px" @change="loadSyncTasks">
            <option value="">全部状态</option>
            <option value="queued">排队中</option>
            <option value="running">运行中</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
          </select>
          <AppButton :disabled="syncTasksLoading" @click="loadSyncTasks">刷新任务</AppButton>
          <span class="muted">展示当前账号最近同步记录，服务重启后仍可恢复查看。</span>
        </div>
        <EmptyState v-if="syncTasksAvailable === false" icon="⚠" title="同步任务历史暂不可用" description="无法读取持久化任务记录，未知状态不会显示为零条任务。">
          <template #actions><AppButton :loading="syncTasksLoading" @click="loadSyncTasks">重试加载</AppButton></template>
        </EmptyState>
        <EmptyState v-else-if="syncTasksAvailable === null" icon="↗" title="请选择一个账号" description="选择账号后可查看该账号的持久化同步任务历史。" />
        <BaseTable v-else :columns="syncCols" :rows="syncTasks">
          <template #status="{row}"><Badge :type="syncStatusType(row.status)">{{ syncStatusText(row.status) }}</Badge></template>
          <template #progress="{row}">{{ Number(row.progress || 0) }}%</template>
          <template #summary="{row}">总 {{ row.total || 0 }} / 新增 {{ row.newCount || 0 }} / 更新 {{ row.updatedCount || 0 }} / 跳过 {{ row.skippedCount || 0 }}</template>
          <template #error="{row}"><span :title="row.errorMessage">{{ shortText(row.errorMessage || '-', 30) }}</span></template>
        </BaseTable>
        <div v-if="syncTasksAvailable === true" class="pagination"><span>{{ syncTasksLoading ? '加载中...' : `共 ${syncTaskTotal} 条任务` }}</span><button type="button" class="page-no" :disabled="syncTasksLoading || syncQuery.current <= 1" aria-label="上一页同步任务" @click="prevSyncPage">‹</button><span class="page-no active" aria-current="page">{{ syncQuery.current }}</span><button type="button" class="page-no" :disabled="syncTasksLoading || syncQuery.current * syncQuery.size >= syncTaskTotal" aria-label="下一页同步任务" @click="nextSyncPage">›</button></div>
      </CardPanel>
    </div>
    <div v-if="selected && listAvailable === true" class="right-drawer products-drawer">
      <div class="drawer-header">
        <h3>商品详情</h3>
        <button class="drawer-close" @click="selected = null">×</button>
      </div>
      <template v-if="selected">
        <div class="preview-card" style="height:210px;padding:0;overflow:hidden;border-radius:12px"><img v-if="selected.coverPic" :src="selected.coverPic" style="width:100%;height:100%;object-fit:cover" alt=""><div v-else class="product-thumb" style="width:100%;height:100%;border-radius:0;background:linear-gradient(135deg,#f5f7fb,#dfe9f8)"></div></div>
        <h3 class="drawer-title">{{ selected.name }}</h3>
        <p class="drawer-price"><b style="color:#ef4444;font-size:22px">{{ selected.price }}</b> <Badge :type="selected.statusType">{{ selected.status }}</Badge></p>
        <CardPanel title="商品数据" class="drawer-card">
          <div class="option-line"><span>商品ID</span><b class="drawer-value">{{ selected.xyGoodId }}</b></div>
          <div class="option-line"><span>库存</span><b>{{ selected.stock }}</b></div>
          <div class="option-line"><span>曝光/浏览/想要</span><b>{{ selected.exposureCount }} / {{ selected.viewCount }} / {{ selected.wantCount }}</b></div>
          <div class="option-line"><span>更新时间</span><b>{{ selected.time }}</b></div>
        </CardPanel>
        <div class="grid drawer-metrics">
          <div class="metric-tile"><span>自动发货</span><b :class="{'text-green':selected.deliveryOn,'text-gray':!selected.deliveryOn}">{{ selected.deliveryOn ? '已开启' : '已关闭' }}</b></div>
          <div class="metric-tile"><span>自动回复</span><b :class="{'text-green':selected.replyOn,'text-gray':!selected.replyOn}">{{ selected.replyOn ? '已开启' : '已关闭' }}</b></div>
          <div class="metric-tile"><span>账号</span><b>{{ accountName(accounts.find(a => a.id === Number(selected.xianyuAccountId)) || {}) || '-' }}</b></div>
        </div>
        <div class="grid drawer-actions">
          <AppButton type="primary" @click="loadDetail(selected)">详情</AppButton>
          <AppButton
            v-if="!selected.isLocalDraft && selected.statusCode === 0"
            type="primary"
            :disabled="productPolishBusy(selected)"
            :loading="productPolishActionLoading(selected)"
            :loading-text="productPolishButtonText(selected, '擦亮商品')"
            :title="itemPolishRetryGuidance(productPolishTask(selected)) || productPolishTask(selected)?.message || '擦亮当前商品'"
            @click="polishProduct(selected)"
          >
            {{ productPolishButtonText(selected, '擦亮商品') }}
          </AppButton>
          <AppButton :disabled="isOffShelfBlockingOtherWrites(selected)" @click="editPrice(selected)">改价</AppButton>
          <AppButton :disabled="isOffShelfBlockingOtherWrites(selected)" @click="editStock(selected)">库存</AppButton>
          <AppButton v-if="selected.isLocalDraft" type="primary" @click="publishDraft(selected)">发布</AppButton>
          <AppButton v-else type="warn" :disabled="isOffShelfLocked(selected) || selected.statusCode !== 0" @click="offShelf(selected.raw)">{{ offShelfButtonText(selected) }}</AppButton>
          <AppButton type="danger" class="full-width" @click="deleteProduct(selected)">删除</AppButton>
        </div>
        <ItemPolishUnknownReconcile
          v-if="selectedProductPolishTask"
          :task="selectedProductPolishTask"
          :busy-goods-id="selectedProductPolishReconcileBusyGoodsId"
          :error-message="selectedProductPolishReconcileMessage"
          @reconcile="reconcileSelectedProductPolishTask"
        />
      </template>
    </div>
  </div>
</template>
<script>
export function createItemPolishPageSingleFlight({ onPhaseChange = () => {} } = {}) {
  const flights = new Map()

  function notify(scopeKey, phase) {
    onPhaseChange(scopeKey, phase)
  }

  function clear(scopeKey, expectedFlight) {
    if (flights.get(scopeKey) !== expectedFlight) return
    flights.delete(scopeKey)
    notify(scopeKey, '')
  }

  function phaseFor(scopeKey) {
    return flights.get(String(scopeKey || ''))?.phase || ''
  }

  function requestDefinitelyNotIssued(error) {
    return error?.polishConflict
      || error?.data?.requestIssued === false
      || error?.data?.platformRequestIssued === false
      || (error?.data?.status === 'failed' && error?.data?.retrySafe === true)
  }

  function run(rawScopeKey, { confirm, submit, taskAfterFailure = () => null } = {}) {
    const scopeKey = String(rawScopeKey || '')
    if (!scopeKey) return Promise.reject(new Error('item polish scope key is required'))
    const active = flights.get(scopeKey)
    if (active) return active.promise

    const flight = { phase: 'confirming', promise: null }
    flights.set(scopeKey, flight)
    notify(scopeKey, flight.phase)
    flight.promise = (async () => {
      let requestIssued = false
      try {
        const confirmed = await confirm()
        if (!confirmed) {
          clear(scopeKey, flight)
          return null
        }
        flight.phase = 'submitting'
        notify(scopeKey, flight.phase)
        requestIssued = true
        const task = await submit()
        clear(scopeKey, flight)
        return task
      } catch (error) {
        const persistedTask = taskAfterFailure()
        if (!requestIssued || requestDefinitelyNotIssued(error) || persistedTask) {
          clear(scopeKey, flight)
        } else {
          flight.phase = 'unknown'
          notify(scopeKey, flight.phase)
        }
        throw error
      }
    })()
    return flight.promise
  }

  return { phaseFor, run }
}
</script>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import StatCard from '../components/StatCard.vue';import CardPanel from '../components/CardPanel.vue';import BaseTable from '../components/BaseTable.vue';import Badge from '../components/Badge.vue';import ToggleSwitch from '../components/ToggleSwitch.vue';import AppButton from '../components/AppButton.vue';import EmptyState from '../components/EmptyState.vue'
import { confirmAction } from '../utils/confirmAction.js'
import { globalConfirm } from '../composables/confirmState.js'
import { getAccounts } from '../api/accounts.js'
import { useItemPolish } from '../composables/useItemPolish.js'
import ItemPolishConflictCard from '../components/ItemPolishConflictCard.vue'
import ItemPolishUnknownReconcile from '../components/ItemPolishUnknownReconcile.vue'
import { getBusinessSettings } from '../api/businessSettings.js'
import { updateProductAutoReplyScope } from '../api/autoReplyScope.js'
import { deleteGoodsLocal, getGoodsDetail, getGoods, getGoodsStats, updateGoods } from '../api/goods.js'
import { refreshItems, getSyncProgress, getSyncTasks, publishItem, offShelfItem, updateItemPrice, remoteDeleteItem } from '../api/items.js'
import { accountName, formatMoney, formatNumber, shortText } from '../utils/format.js'
import { accountAuthState } from '../utils/accountAuth.js'
import {
  itemPolishBlocksRetry,
  itemPolishCanStartNextBusinessDay,
  itemPolishCanResume,
  itemPolishRetryGuidance,
  itemPolishScopeKey,
  itemPolishStatusText,
} from '../utils/itemPolishState.js'

const emit = defineEmits(['navigate'])
const accounts = ref([])
const items = ref([])
const totalCount = ref(0)
const goodsStats = ref({ total: 0, onSale: 0, offShelfOrDraft: 0, autoDeliveryOn: 0, autoReplyAccounts: 0 })
const listAvailable = ref(null)
const statsAvailable = ref(null)
const loading = ref(false)
const syncing = ref(false)
const busyItemId = ref(null)
// 批量选择：使用商品记录的本地 id（raw.id）作为 key，翻页/筛选时清空，避免误删不可见行
const selectedKeys = ref([])
const batchDeleting = ref(false)
const batchDeleteState = reactive({
  active: false,
  done: 0,
  total: 0,
  current: '',
  result: null // { success: number, failed: [{name, reason}] }
})
const rowKeyFn = (row) => row?.raw?.id
const batchDeleteBtnText = computed(() => {
  if (batchDeleting.value) {
    return `删除中 ${batchDeleteState.done}/${batchDeleteState.total}`
  }
  return selectedKeys.value.length ? `批量删除(${selectedKeys.value.length})` : '批量删除'
})
const syncTask = ref({ id: '', status: '', progress: 0 })
const syncTasks = ref([])
const syncTaskTotal = ref(0)
const syncTasksLoading = ref(false)
const syncTasksAvailable = ref(null)
const syncQuery = reactive({ status: '', current: 1, size: 5 })
const notice = ref({ type: '', text: '' })
const selected = ref(null)
const query = reactive({ xianyuAccountId: '', status: '', keyword: '', pageNum: 1, pageSize: 50 })
const polishConflictScope = ref(null)
const {
  submit: submitItemPolish,
  restore: restoreItemPolish,
  taskFor: storedPolishTaskFor,
  pollMessageFor: polishPollMessageFor,
  conflictFor: polishConflictFor,
  refreshConflict: refreshPolishConflict,
  conflictRefreshingFor: polishConflictRefreshingFor,
  conflictRefreshMessageFor: polishConflictRefreshMessageFor,
  clearAllConflicts: clearAllPolishConflicts,
  reconcile: reconcilePolishTask,
  reconcilingGoodsIdFor: polishReconcilingGoodsIdFor,
  reconcileMessageFor: polishReconcileMessageFor,
} = useItemPolish()
const POLISH_BUSY_TASK_STATUSES = new Set(['pending', 'running', 'unknown'])
const polishFlightPhases = reactive({})
const polishSingleFlight = createItemPolishPageSingleFlight({
  onPhaseChange(scopeKey, phase) {
    if (phase) polishFlightPhases[scopeKey] = phase
    else delete polishFlightPhases[scopeKey]
  },
})
const currentAccountPolishTask = computed(() => query.xianyuAccountId ? storedPolishTaskFor(query.xianyuAccountId) : null)
const currentAccountPolishPollMessage = computed(() => query.xianyuAccountId ? polishPollMessageFor(query.xianyuAccountId) : '')
const activePolishConflict = computed(() => {
  const target = polishConflictScope.value
  return target ? polishConflictFor(target.accountId, target.goodsIds) : null
})
const activePolishConflictRefreshing = computed(() => {
  const target = polishConflictScope.value
  return target ? polishConflictRefreshingFor(target.accountId, target.goodsIds) : false
})
const activePolishConflictRefreshMessage = computed(() => {
  const target = polishConflictScope.value
  return target ? polishConflictRefreshMessageFor(target.accountId, target.goodsIds) : ''
})
const currentAccountPolishReconcileBusyGoodsId = computed(() => query.xianyuAccountId ? polishReconcilingGoodsIdFor(query.xianyuAccountId) : 0)
const currentAccountPolishReconcileMessage = computed(() => query.xianyuAccountId ? polishReconcileMessageFor(query.xianyuAccountId) : '')
const selectedProductPolishTask = computed(() => selected.value ? productPolishTask(selected.value) : null)
const selectedProductPolishReconcileBusyGoodsId = computed(() => {
  const target = selected.value ? productPolishScope(selected.value) : null
  return target?.accountId && target.goodsIds.length ? polishReconcilingGoodsIdFor(target.accountId, target.goodsIds) : 0
})
const selectedProductPolishReconcileMessage = computed(() => {
  const target = selected.value ? productPolishScope(selected.value) : null
  return target?.accountId && target.goodsIds.length ? polishReconcileMessageFor(target.accountId, target.goodsIds) : ''
})
// 每页条数可选项，默认 50
const pageSizes = [50, 100, 200, 300, 500, 1000]
const cols=[{key:'info',title:'商品信息'},{key:'price',title:'价格'},{key:'stock',title:'库存'},{key:'sku',title:'SKU'},{key:'status',title:'状态'},{key:'type',title:'发货类型'},{key:'reply',title:'自动回复'},{key:'onsale',title:'在售'},{key:'time',title:'更新时间'},{key:'op',title:'操作'}]
const syncCols=[{key:'createdTime',title:'创建时间'},{key:'status',title:'状态'},{key:'progress',title:'进度'},{key:'summary',title:'统计'},{key:'durationSeconds',title:'耗时(s)'},{key:'error',title:'错误'}]
let syncPollCanceled = false
const statusMap = { 0: '在售', 1: '下架/草稿', 2: '已售出', 3: '已删除' }
const autoSyncState = reactive({
  active: false,
  completed: false,
  partial: false,
  error: '',
  progress: 0,
  summary: { total: 0, new: 0, updated: 0, offShelf: 0, duration: 0 },
  // 多账号顺序同步时的进度信息
  accountIndex: 0,
  accountTotal: 0,
  accountLabel: '',
  failedAccounts: []
})
const AUTO_DELIVERY_FOCUS_GOODS_KEY = 'xya:auto-delivery-focus-goods-id'
const EXTERNAL_OPERATION_INTENTS_KEY = 'xya:product-external-operation-intents'
const publishDraftIntents = reactive({})
const priceIntents = reactive({})
const offShelfIntents = reactive({})

function createExternalOperationKey(prefix) {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `${prefix}-${globalThis.crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function saveExternalOperationIntents() {
  try {
    sessionStorage.setItem(EXTERNAL_OPERATION_INTENTS_KEY, JSON.stringify({
      publish: publishDraftIntents,
      price: priceIntents,
      offShelf: offShelfIntents,
    }))
  } catch { /* Session recovery is best-effort. */ }
}

function restoreExternalOperationIntents() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(EXTERNAL_OPERATION_INTENTS_KEY) || 'null')
    if (saved?.publish && typeof saved.publish === 'object') Object.assign(publishDraftIntents, saved.publish)
    if (saved?.price && typeof saved.price === 'object') Object.assign(priceIntents, saved.price)
    if (saved?.offShelf && typeof saved.offShelf === 'object') Object.assign(offShelfIntents, saved.offShelf)
  } catch { /* Ignore invalid session state. */ }
}

function clearExternalOperationIntent(bucket, key) {
  delete bucket[key]
  saveExternalOperationIntents()
}

function reconcileOffShelfIntents(records = []) {
  let changed = false
  for (const wrapper of records) {
    const item = wrapper?.item || wrapper
    const goodsKey = String(item?.id || '')
    const persisted = item?.offShelfAttempt
    const intent = offShelfIntents[goodsKey]
    if (!goodsKey || !persisted || !intent) continue
    if (persisted.status === 'confirmed') {
      delete offShelfIntents[goodsKey]
      changed = true
      continue
    }
    Object.assign(intent, {
      status: persisted.status,
      retrySafe: persisted.retrySafe === true,
      recovery: persisted.recovery || null,
    })
    changed = true
  }
  if (changed) saveExternalOperationIntents()
}

const products = computed(() => items.value.map(w => {
  const item = w.item || w
  const statusCode = Number(item.status ?? 1)
  const category = item.category || ''
  const externalId = item.externalGoodsId || item.xyGoodId || ''
  const isLocalDraft = category === '商机发掘' || String(externalId).startsWith('opp:') || !externalId
  return {
    raw: item,
    wrapper: w,
    name: shortText(item.title || '未命名商品', 34),
    xyGoodId: externalId || `local:${item.id}`,
    category,
    isLocalDraft,
    xianyuAccountId: item.accountId || item.xianyuAccountId,
    remoteDeleteAttempt: item.remoteDeleteAttempt || null,
    offShelfAttempt: item.offShelfAttempt || null,
    coverPic: item.imageUrl || item.mainImageUrl || item.coverPic,
    price: formatMoney(item.soldPrice ?? item.price),
    stock: item.stock ?? item.quantity ?? '-',
    sku: item.skuCount || '-',
    statusCode,
    status: isLocalDraft ? '草稿/待发布' : (statusMap[statusCode] || String(statusCode)),
    statusType: isLocalDraft ? 'orange' : (statusCode === 0 ? 'green' : statusCode === 3 ? 'red' : 'orange'),
    type: w.autoDeliveryType === 0 ? '卡密' : w.autoDeliveryType === 1 ? '文本' : w.autoDeliveryType === 2 ? '自定义' : '未配置',
    deliveryOn: w.xianyuAutoDeliveryOn === 1,
    replyOn: w.xianyuAutoReplyOn === 1,
    time: item.updatedTime || item.createdTime || '-',
    exposureCount: formatNumber(item.exposureCount),
    viewCount: formatNumber(item.viewCount),
    wantCount: formatNumber(item.wantCount)
  }
}))
const selectedAccountName = computed(() => accountName(accounts.value.find(a => a.id === Number(query.xianyuAccountId)) || {}))
// AI 客服主开关与读取可用性分开保存；读取失败绝不能等同于“已关闭”。
const aiCsEnabledCache = ref(null)
const aiCsAvailable = ref(null)

async function checkAiCsEnabled() {
  if (aiCsAvailable.value === true) return aiCsEnabledCache.value
  try {
    const res = await getBusinessSettings('ai-customer-service')
    const data = res?.data ?? res
    aiCsEnabledCache.value = data?.enabled === true
    aiCsAvailable.value = true
    return aiCsEnabledCache.value
  } catch {
    aiCsAvailable.value = false
    aiCsEnabledCache.value = null
    if (import.meta.env.DEV) console.warn('[ProductsPage] 检查AI客服主开关失败')
    return null
  }
}

async function promptEnableAiCs() {
  const ok = await confirmAction({
    title: '尚未开启 AI 自动回复主开关',
    description: '请先前往「AI 客服配置」页面启用 AI 自动回复并设置工作时段；实际运行还依赖模型、账号连接和平台状态。',
    confirmText: '前往配置'
  })
  if (ok) emit('navigate', 'settings-ai-cs')
}
function showNotice(type, text) { notice.value = { type, text } }
function clearNotice() { notice.value = { type: '', text: '' } }
function ensureListAvailable(action = '执行该操作') {
  if (listAvailable.value === true) return true
  showNotice('warn', `商品列表暂不可用，无法确认当前状态，已安全阻止${action}。请先重试加载。`)
  return false
}

function productPolishScope(row) {
  const goodsId = Number(row?.raw?.id || row?.id || 0)
  const accountId = Number(row?.xianyuAccountId || row?.raw?.accountId || row?.raw?.xianyuAccountId || query.xianyuAccountId || 0)
  return { accountId, goodsIds: goodsId > 0 ? [goodsId] : [] }
}

function polishScopeKeyFor(accountId, goodsIds = []) {
  return itemPolishScopeKey(accountId, goodsIds)
}

function polishFlightPhaseFor(accountId, goodsIds = []) {
  return polishFlightPhases[polishScopeKeyFor(accountId, goodsIds)] || ''
}

function isPolishScopeReconciling(accountId, goodsIds = []) {
  return Boolean(accountId && polishReconcilingGoodsIdFor(accountId, goodsIds))
}

function polishScopeTask(accountId, goodsIds = []) {
  return accountId ? storedPolishTaskFor(accountId, goodsIds) : null
}

function isPolishScopeBusy(accountId, goodsIds = []) {
  if (!Number(accountId)) return false
  const task = polishScopeTask(accountId, goodsIds)
  return Boolean(
    polishFlightPhaseFor(accountId, goodsIds)
      || POLISH_BUSY_TASK_STATUSES.has(String(task?.status || ''))
      || isPolishScopeReconciling(accountId, goodsIds)
      || itemPolishBlocksRetry(task)
      || polishConflictFor(accountId, goodsIds),
  )
}

function isPolishScopeActionLoading(accountId, goodsIds = []) {
  return ['confirming', 'submitting'].includes(polishFlightPhaseFor(accountId, goodsIds))
    || isPolishScopeReconciling(accountId, goodsIds)
}

function polishScopeButtonText(accountId, goodsIds = [], fallback = '擦亮') {
  const phase = polishFlightPhaseFor(accountId, goodsIds)
  if (phase === 'confirming') return '确认中...'
  if (phase === 'submitting') return '提交中...'
  if (phase === 'unknown') return '结果待核对'
  if (isPolishScopeReconciling(accountId, goodsIds)) return '核对结果中...'
  const task = polishScopeTask(accountId, goodsIds)
  if (task?.status === 'pending') {
    return task.recovery === 'resume_task' ? '提交待确认' : '等待执行'
  }
  return task ? itemPolishStatusText(task) : fallback
}

function productPolishTask(row) {
  const target = productPolishScope(row)
  return target.accountId && target.goodsIds.length
    ? storedPolishTaskFor(target.accountId, target.goodsIds)
    : null
}

function productPolishBusy(row) {
  const target = productPolishScope(row)
  return isPolishScopeBusy(target.accountId, target.goodsIds)
}

function productPolishActionLoading(row) {
  const target = productPolishScope(row)
  return isPolishScopeActionLoading(target.accountId, target.goodsIds)
}

function productPolishButtonText(row, fallback = '擦亮') {
  const target = productPolishScope(row)
  return polishScopeButtonText(target.accountId, target.goodsIds, fallback)
}

function setActivePolishConflictScope(accountId, goodsIds = []) {
  const next = { accountId: Number(accountId), goodsIds: [...goodsIds] }
  const current = polishConflictScope.value
  if (!current || itemPolishScopeKey(current.accountId, current.goodsIds) !== itemPolishScopeKey(next.accountId, next.goodsIds)) {
    clearAllPolishConflicts()
    if (current) clearNotice()
  }
  polishConflictScope.value = next
}

function clearActivePolishConflict() {
  clearAllPolishConflicts()
  polishConflictScope.value = null
  clearNotice()
}

async function refreshActivePolishConflict() {
  const target = polishConflictScope.value
  if (!target) return
  await refreshPolishConflict(target.accountId, target.goodsIds)
}

async function reconcileItemPolishTask({ goodsId, outcome }, target) {
  if (!target?.accountId) return
  try {
    await reconcilePolishTask({
      accountId: target.accountId,
      goodsIds: target.goodsIds || [],
      goodsId,
      outcome,
    })
    showNotice(
      'success',
      outcome === 'confirmed_not_polished'
        ? '该商品已记录为今天未擦亮。为防迟到请求重复操作，本日不再自动重试，次日可新建任务。'
        : '该商品的人工核对结论已记录，原任务状态已更新。',
    )
  } catch {
    showNotice('error', '人工核对结论保存失败；原任务快照已保留，可在网络恢复后重试当前这一项。')
  }
}

async function reconcileCurrentAccountPolishTask(payload) {
  await reconcileItemPolishTask(payload, { accountId: Number(query.xianyuAccountId), goodsIds: [] })
}

async function reconcileSelectedProductPolishTask(payload) {
  if (!selected.value) return
  await reconcileItemPolishTask(payload, productPolishScope(selected.value))
}

function polishNoticeType(status) {
  return {
    completed: 'success',
    running: 'info',
    pending: 'info',
    partial: 'warn',
    failed: 'error',
    needs_verification: 'warn',
    unknown: 'warn',
  }[status] || 'info'
}

async function executePolishScope({ accountId, goodsIds = [], label = '在售商品' }) {
  if (!ensureListAvailable('擦亮商品')) return null
  if (isPolishScopeBusy(accountId, goodsIds)) return polishScopeTask(accountId, goodsIds)
  const account = accounts.value.find(value => Number(value.id) === Number(accountId))
  const authState = accountAuthState(account || {})
  if (authState !== true) {
    showNotice(
      authState === false ? 'error' : 'warn',
      authState === false
        ? '账号登录状态不可用，请先到闲鱼账号页重新扫码或更新 Cookie。'
        : '账号登录状态尚未确认，请先到闲鱼账号页执行登录验证。',
    )
    return null
  }
  setActivePolishConflictScope(accountId, goodsIds)
  const existingConflict = polishConflictFor(accountId, goodsIds)
  if (existingConflict) {
    showNotice(
      'warn',
      existingConflict.existingTask?.status === 'unknown'
        ? '既有任务结果未知，当前继续禁止重试或重新提交；请只刷新冲突卡片并在闲鱼 App 核对。'
        : '该范围仍有既有任务冲突；请使用冲突卡片只读刷新状态，不要重复提交。',
    )
    return existingConflict.existingTask
  }
  const currentTask = storedPolishTaskFor(accountId, goodsIds)
  if (itemPolishBlocksRetry(currentTask)) {
    const retryGuidance = itemPolishRetryGuidance(currentTask)
    showNotice(
      'warn',
      retryGuidance || (currentTask.status === 'unknown'
        ? '上次擦亮结果未知，请先在闲鱼 App 核对；系统不会自动或手动重复提交该未知任务。'
        : '闲鱼要求完成安全验证，请先在闲鱼 App 验证；当前页面不会自动重试。'),
    )
    return currentTask
  }
  const isResume = itemPolishCanResume(currentTask)
  const isVerificationResume = currentTask?.status === 'needs_verification'
  const isNextBusinessDayTask = itemPolishCanStartNextBusinessDay(currentTask)
  const confirmation = isNextBusinessDayTask
    ? {
        title: '新建次日擦亮任务？',
        description: `${itemPolishRetryGuidance(currentTask)} 本次提交会创建新的任务和幂等键，绝不会复用昨日终态。`,
        confirmText: '新建任务并擦亮',
      }
    : {
        title: isVerificationResume ? '确认已完成闲鱼安全验证？' : (isResume ? '继续安全擦亮任务？' : `确认擦亮${label}？`),
        description: isVerificationResume
          ? '仅当你已在闲鱼 App 完成安全验证时继续。系统会复用原任务、原商品范围和原幂等键，不创建新意图。'
          : isResume
          ? '将复用原任务、原商品范围和原幂等键，只恢复明确可安全执行的项目；未知结果不会重试。'
          : '服务端会先持久化逐项意图，再调用真实闲鱼擦亮接口。超时或连接中断会标记为结果未知并停止自动重试。',
        confirmText: isVerificationResume ? '我已完成验证，继续原任务' : (isResume ? '继续原任务' : '开始擦亮'),
      }
  try {
    const task = await polishSingleFlight.run(polishScopeKeyFor(accountId, goodsIds), {
      confirm: () => confirmAction(confirmation),
      submit: () => submitItemPolish({
        accountId,
        goodsIds,
        forceNew: currentTask?.status === 'completed',
      }),
      taskAfterFailure: () => storedPolishTaskFor(accountId, goodsIds),
    })
    if (!task) return null
    showNotice(polishNoticeType(task.status), task.message)
    return task
  } catch (error) {
    const preserved = storedPolishTaskFor(accountId, goodsIds)
    const resultUnknown = polishFlightPhaseFor(accountId, goodsIds) === 'unknown'
    showNotice(
      resultUnknown || error?.timeout || error?.code === 'NETWORK_ERROR' ? 'warn' : 'error',
      resultUnknown
        ? '擦亮请求是否已签发尚未确认，当前意图已锁定。请先在闲鱼 App 核对并刷新任务状态，系统不会重复提交。'
        : error?.polishConflict?.message || preserved?.message || error?.message || '擦亮任务提交失败，请检查账号与商品状态。',
    )
    return preserved
  }
}

async function polishCurrentAccount() {
  const accountId = Number(query.xianyuAccountId || 0)
  if (!accountId) {
    showNotice('warn', '请先选择一个闲鱼账号，再执行账号级一键擦亮。')
    return
  }
  await executePolishScope({ accountId, label: '当前账号全部在售商品' })
}

async function polishProduct(row) {
  const target = productPolishScope(row)
  if (!target.accountId || !target.goodsIds.length) {
    showNotice('warn', '缺少有效账号或本地商品标识，无法建立安全擦亮意图。')
    return
  }
  selectProduct(row)
  await executePolishScope({ ...target, label: `商品“${row?.name || '当前商品'}”` })
}
function setStatus(status){ query.status = status; query.pageNum = 1; selectedKeys.value = []; loadItems() }
function resetQuery(){ query.status=''; query.keyword=''; query.pageNum=1; selectedKeys.value = []; loadItems() }
function onAccountChange(){
  clearActivePolishConflict()
  query.pageNum = 1
  selectedKeys.value = []
  syncQuery.current = 1
  loadSyncTasks()
  loadGoodsStats()
  // 切换账号时重新检查自动同步条件
  autoTriggerSync()
}

async function loadAccountsData() {
  const res = await getAccounts()
  const list = Array.isArray(res.data) ? res.data : (res.data?.records || res.data?.accounts || res.data?.list || res.data?.rows || [])
  accounts.value = list
  // 默认不选中任何账号，即"全部账号"；用户需要单独查看某账号时手动选择
}
async function loadItems(options = {}) {
  loading.value = true
  try {
    const selectedGoodsId = selected.value?.raw?.id ?? selected.value?.id ?? null
    const params = { pageNum: query.pageNum, pageSize: query.pageSize, keyword: query.keyword || undefined }
    if (query.xianyuAccountId) params.xianyuAccountId = Number(query.xianyuAccountId)
    if (query.status !== '') params.status = query.status
    // 支持排除特定状态，例如同步完成后排除已删除(status=3)商品
    if (options.excludeStatus !== undefined) params.excludeStatus = options.excludeStatus
    const res = await getGoods(params)
    const data = res.data || {}
    const records = data.records || data.itemsWithConfig || data.items || data.list || data.rows || (Array.isArray(data) ? data : null)
    const total = data.total ?? data.totalCount
    if (!Array.isArray(records) || !Number.isFinite(Number(total))) throw new Error('商品列表响应结构无效')
    items.value = records
    totalCount.value = Number(total)
    listAvailable.value = true
    reconcileOffShelfIntents(items.value)
    selected.value = products.value.find(product => Number(product.raw?.id || product.id) === Number(selectedGoodsId)) || products.value[0] || null
    return true
  } catch (e) {
    items.value = []
    totalCount.value = 0
    selected.value = null
    selectedKeys.value = []
    listAvailable.value = false
    showNotice('error', e.message || '商品列表加载失败，相关写操作已禁用')
    return false
  }
  finally { loading.value = false }
}
// 加载商品全局统计（不受分页、关键词、状态筛选影响，仅按账号过滤）
async function loadGoodsStats() {
  try {
    const params = {}
    if (query.xianyuAccountId) params.accountId = Number(query.xianyuAccountId)
    const res = await getGoodsStats(params)
    const data = res?.data ?? res
    const requiredStats = ['total', 'onSale', 'offShelfOrDraft', 'autoDeliveryOn', 'autoReplyAccounts']
    if (!data || typeof data !== 'object' || Array.isArray(data)
      || requiredStats.some(key => {
        const num = Number(data[key])
        return data[key] === null || data[key] === undefined || data[key] === '' || !Number.isFinite(num) || num < 0
      })) {
      throw new Error('商品统计响应不完整')
    }
    goodsStats.value = {
      total: Number(data.total),
      onSale: Number(data.onSale),
      offShelfOrDraft: Number(data.offShelfOrDraft),
      autoDeliveryOn: Number(data.autoDeliveryOn),
      autoReplyAccounts: Number(data.autoReplyAccounts)
    }
    statsAvailable.value = true
  } catch {
    statsAvailable.value = false
    if (import.meta.env.DEV) console.warn('[ProductsPage] 商品统计加载失败')
  }
}
async function loadSyncTasks() {
  if (!query.xianyuAccountId) {
    syncTasks.value = []
    syncTaskTotal.value = 0
    syncTasksAvailable.value = null
    return
  }
  syncTasksLoading.value = true
  try {
    const res = await getSyncTasks({ accountId: Number(query.xianyuAccountId), status: syncQuery.status || undefined, current: syncQuery.current, size: syncQuery.size })
    const page = res.data || {}
    if (!Array.isArray(page.records) || !Number.isFinite(Number(page.total))) throw new Error('同步任务响应结构无效')
    syncTasks.value = page.records
    syncTaskTotal.value = Number(page.total)
    syncTasksAvailable.value = true
  } catch (e) {
    syncTasks.value = []
    syncTaskTotal.value = 0
    syncTasksAvailable.value = false
    showNotice('error', e.message || '同步任务历史加载失败')
  } finally { syncTasksLoading.value = false }
}
function syncStatusText(status) { return ({ queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' })[status] || status || '-' }
function syncStatusType(status) { return status === 'completed' ? 'green' : status === 'failed' ? 'red' : status === 'running' ? 'orange' : 'gray' }
function prevSyncPage(){ if(syncQuery.current > 1){ syncQuery.current--; loadSyncTasks() } }
function nextSyncPage(){ if(syncQuery.current * syncQuery.size < syncTaskTotal.value){ syncQuery.current++; loadSyncTasks() } }
async function init(){
  try {
    await loadAccountsData()
  } catch {
    // 账号加载失败不阻塞：商品列表/统计/任务历史仍可独立加载
  }
  try { await loadSyncTasks() } catch(e) { if (import.meta.env.DEV) console.warn('[ProductsPage] 同步任务历史加载失败', e) }
  try { loadGoodsStats() } catch(e) { if (import.meta.env.DEV) console.warn('[ProductsPage] 商品统计加载失败', e) }
  // 进入页面后自动触发闲鱼商品同步（无需用户手动点击）
  autoTriggerSync()
}
function showAllProducts() {
  // 用户点击"查看全部商品"时清除仅展示同步结果的限制，加载全部商品
  autoSyncState.completed = false
  loadItems()
}
function selectProduct(row) {
  const active = polishConflictScope.value
  const target = productPolishScope(row)
  if (active && itemPolishScopeKey(active.accountId, active.goodsIds) !== itemPolishScopeKey(target.accountId, target.goodsIds)) {
    clearActivePolishConflict()
  }
  selected.value = row
}
const rowClass = (row) => selected.value && selected.value.xyGoodId === row.xyGoodId ? 'row-selected' : ''
function itemBusyKey(row){ return row?.raw?.id || row?.id || row?.xyGoodId }
function isItemBusy(row){ return busyItemId.value && busyItemId.value === itemBusyKey(row) }
async function withItemBusy(row, task){ const key = itemBusyKey(row); if (busyItemId.value) return; busyItemId.value = key; try { return await task() } finally { busyItemId.value = null } }
function remoteDeleteKey(item){ return `remote-delete:${item.id}` }
function remoteDeleteStatusText(row) {
  const state = row?.remoteDeleteAttempt?.status
  return {
    pending: '删除待执行',
    in_progress: '平台删除中',
    remote_confirmed: '待完成本地删除',
    failed: '平台已拒绝',
    unknown: '结果未知，需人工核对',
  }[state] || '删除状态待核对'
}
function isRemoteDeleteLocked(row) {
  return ['pending', 'in_progress', 'unknown'].includes(row?.remoteDeleteAttempt?.status)
}
function remoteDeleteButtonText(row) {
  if (isItemBusy(row)) return '处理中'
  return {
    pending: '等待执行',
    in_progress: '删除中',
    remote_confirmed: '完成本地删除',
    failed: '重试删除',
    unknown: '需人工核对',
  }[row?.remoteDeleteAttempt?.status] || '删除'
}
function remoteDeleteFailure(error) {
  if (error?.timeout || ['TIMEOUT', 'NETWORK_ERROR'].includes(error?.code)) {
    return { type: 'warn', message: '请求结果未确认，请先在闲鱼 App 核对；不要立即重复删除。' }
  }
  const state = error?.data?.status || 'failed'
  switch (state) {
    case 'unknown':
      return { type: 'warn', message: '平台删除结果未知，请先在闲鱼 App 核对；系统不会自动重试。' }
    case 'remote_confirmed':
      return { type: 'warn', message: '平台删除已确认，但本地软删除尚未完成；再次操作只会重试本地收尾。' }
    case 'in_progress':
    case 'pending':
      return { type: 'info', message: '该商品的删除正在执行，请勿重复操作。' }
    default:
      return { type: 'error', message: error?.message || '平台明确拒绝删除，本地商品保持不变。' }
  }
}
function offShelfAttemptOf(value) {
  return value?.offShelfAttempt || value?.raw?.offShelfAttempt || null
}
function offShelfStatusText(row) {
  const attempt = offShelfAttemptOf(row)
  return {
    pending: '下架待执行',
    in_progress: '平台下架中',
    remote_confirmed: '待完成本地状态',
    failed: attempt?.retrySafe ? '未执行，可重试' : '失败，需人工核对',
    unknown: '下架结果未知，需人工核对',
  }[attempt?.status] || '下架状态待核对'
}
function isOffShelfLocked(row) {
  const attempt = offShelfAttemptOf(row)
  if (!attempt) return false
  return ['pending', 'in_progress', 'unknown'].includes(attempt.status)
    || (attempt.status === 'failed' && attempt.retrySafe !== true)
}
function isOffShelfBlockingOtherWrites(row) {
  const attempt = offShelfAttemptOf(row)
  return isOffShelfLocked(row) || attempt?.status === 'remote_confirmed'
}
function offShelfButtonText(row) {
  if (isItemBusy(row)) return '处理中'
  const attempt = offShelfAttemptOf(row)
  return {
    pending: '等待下架',
    in_progress: '下架中',
    remote_confirmed: '完成本地状态',
    failed: attempt?.retrySafe ? '重试下架' : '需人工核对',
    unknown: '需人工核对',
  }[attempt?.status] || '下架'
}
function offShelfFailure(error) {
  if (error?.timeout || ['TIMEOUT', 'NETWORK_ERROR'].includes(error?.code)) {
    return { state: 'unknown', retrySafe: false, type: 'warn', message: '请求结果未确认，请先在闲鱼 App 核对商品是否已下架；当前禁止重复操作。' }
  }
  const state = String(error?.data?.status || 'failed')
  const retrySafe = error?.data?.retrySafe === true
  if (state === 'unknown') return { state, retrySafe: false, type: 'warn', message: '平台下架结果未知，请先在闲鱼 App 核对；系统不会自动重试。' }
  if (state === 'remote_confirmed') return { state, retrySafe: true, type: 'warn', message: '平台下架已确认，但本地状态尚未完成；再次操作只会修复本地状态。' }
  if (['pending', 'in_progress'].includes(state)) return { state, retrySafe: false, type: 'info', message: '该商品正在下架，请勿重复操作。' }
  return {
    state,
    retrySafe,
    type: retrySafe ? 'error' : 'warn',
    message: retrySafe
      ? (error?.message || '平台明确未执行下架；排除问题后可使用原意图安全重试。')
      : '无法确认平台是否执行，请先在闲鱼 App 核对；当前禁止重试。',
  }
}
function prevPage(){ if(query.pageNum > 1){ query.pageNum--; selectedKeys.value = []; loadItems() } }
function nextPage(){ if(query.pageNum * query.pageSize < totalCount.value){ query.pageNum++; selectedKeys.value = []; loadItems() } }
function goToPage(n){
  const total = Math.max(1, Math.ceil(totalCount.value / query.pageSize))
  if (n < 1 || n > total || n === query.pageNum) return
  query.pageNum = n
  selectedKeys.value = []
  loadItems()
}
// 总页数
const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / query.pageSize)))
// 可点击的页码列表（含省略号）：总是显示首尾页，当前页前后各显示 2 页
const pageList = computed(() => {
  const total = totalPages.value
  const current = query.pageNum
  const list = []
  if (total <= 7) {
    for (let i = 1; i <= total; i++) list.push(i)
    return list
  }
  list.push(1)
  let start = Math.max(2, current - 2)
  let end = Math.min(total - 1, current + 2)
  if (start > 2) list.push('...')
  for (let i = start; i <= end; i++) list.push(i)
  if (end < total - 1) list.push('...')
  list.push(total)
  return list
})
// 切换每页条数：重置到第 1 页并清空选择
function changePageSize() {
  query.pageNum = 1
  selectedKeys.value = []
  loadItems()
}
// select change 事件：转成数字再调用 changePageSize
function onPageSizeChange(e) {
  query.pageSize = Number(e.target.value)
  changePageSize()
}
async function refreshSingle(row) {
  if (!ensureListAvailable('同步商品')) return
  const accountId = row.xianyuAccountId || Number(query.xianyuAccountId)
  if (!accountId) return showNotice('warn', '请先选择账号')
  const ok = await confirmAction({ title:'确认同步该账号全部商品？', description:'当前版本会同步该账号的全部闲鱼商品，不是仅刷新单个商品。同步期间请避免重复点击。' })
  if (!ok) return
  return withItemBusy(row, async () => { try { await refreshItems({ xianyuAccountId: accountId }); showNotice('info', '账号商品同步已提交'); await loadItems(); loadGoodsStats() } catch(e){ showNotice('error', e.message || '刷新失败') } })
}
async function toggleReply(row) {
  if (!ensureListAvailable('切换自动回复')) return
  if (isOffShelfBlockingOtherWrites(row)) return showNotice('warn', '下架流程尚未安全收尾，已阻止修改自动回复范围。')
  if (typeof isItemBusy === 'function' && isItemBusy(row)) return
  const nextEnabled = !row.replyOn
  if (nextEnabled) {
    const enabled = await checkAiCsEnabled()
    if (enabled === null) {
      showNotice('warn', 'AI 客服主开关状态暂不可用，无法确认是否允许开启；操作已安全阻止，请稍后重试。')
      return
    }
    if (enabled === false) {
      await promptEnableAiCs()
      return
    }
  }
  try {
    const itemId = row.raw?.id ?? row.id
    await updateProductAutoReplyScope(itemId, nextEnabled)
    row.replyOn = nextEnabled
    if (row.raw) row.raw.auto_reply_enabled = nextEnabled ? 1 : 0
    showNotice('success', `已${nextEnabled ? '开启' : '关闭'}商品"${row.name}"的自动回复`)
    aiCsAvailable.value = null
    aiCsEnabledCache.value = null
    loadGoodsStats()
  } catch (e) {
    showNotice('error', e.message || '切换自动回复失败')
    aiCsAvailable.value = null
    aiCsEnabledCache.value = null
  }
}
async function toggleOnShelf(row) {
  if (!ensureListAvailable('切换商品上下架状态')) return
  if (isOffShelfLocked(row)) {
    return showNotice('warn', '该商品下架结果尚未安全确认，请先在闲鱼 App 核对并同步商品状态。')
  }
  if (row.isLocalDraft) return publishDraft(row)
  if (row.statusCode === 0) return offShelf(row.raw)
  showNotice('warn', '重新上架需要重新发布商品，即将跳转到发布商品页')
  setTimeout(() => emit('navigate', 'product-publish'), 1200)
}
async function offShelf(item) {
  if (!ensureListAvailable('下架商品')) return
  if(!item?.externalGoodsId) return showNotice('warn', '本地草稿尚未发布到闲鱼，不能执行远端下架')
  const goodsKey = String(item.id || '')
  if (!goodsKey) return showNotice('warn', '缺少本地商品标识，无法建立安全下架意图')
  const persisted = offShelfAttemptOf(item)
  if (isOffShelfLocked(item)) {
    return showNotice('warn', persisted?.message || '下架结果尚未确认，请先在闲鱼 App 核对；当前禁止重复操作。')
  }
  if (persisted?.status === 'confirmed') {
    return showNotice('info', '该商品的平台与本地下架状态均已确认，无需重复操作。')
  }
  if (persisted?.status === 'failed' && persisted.retrySafe !== true) {
    return showNotice('warn', '上次下架无法确认是否执行，请先在闲鱼 App 核对并同步商品状态。')
  }

  let intent = offShelfIntents[goodsKey]
  const isNewIntent = !intent
  if (!intent) {
    intent = {
      idempotencyKey: createExternalOperationKey('off-shelf'),
      status: persisted?.status || 'pending',
      retrySafe: persisted?.retrySafe === true,
      payload: {
        xianyuAccountId: Number(item.accountId || query.xianyuAccountId),
        xyGoodsId: item.externalGoodsId,
      },
    }
    offShelfIntents[goodsKey] = intent
    saveExternalOperationIntents()
  }
  if (!intent.payload.xianyuAccountId) {
    if (isNewIntent) clearExternalOperationIntent(offShelfIntents, goodsKey)
    return showNotice('warn', '缺少有效账号，无法下架商品')
  }

  const onlyRepairLocal = persisted?.status === 'remote_confirmed' || intent.status === 'remote_confirmed'
  const confirmed = await confirmAction({
    title: onlyRepairLocal ? '确认仅修复本地下架状态？' : '确认下架该商品？',
    description: onlyRepairLocal
      ? '闲鱼平台已确认下架。本次只补全本地商品状态，不会再次调用平台下架接口。'
      : '服务端会先持久化下架意图再访问闲鱼。若请求超时或中断，将锁定为结果未知并要求先到闲鱼 App 核对。',
  })
  if (!confirmed) {
    if (isNewIntent) clearExternalOperationIntent(offShelfIntents, goodsKey)
    return
  }
  return withItemBusy({ raw: item }, async () => {
    try {
      await offShelfItem({
        ...intent.payload,
        idempotencyKey: intent.idempotencyKey,
      })
      clearExternalOperationIntent(offShelfIntents, goodsKey)
      showNotice('success', '商品已在闲鱼平台与本地确认下架')
      await loadItems()
      loadGoodsStats()
    } catch(e) {
      const failure = offShelfFailure(e)
      Object.assign(intent, {
        status: failure.state,
        retrySafe: failure.retrySafe,
        recovery: e?.data?.recovery || null,
      })
      saveExternalOperationIntents()
      showNotice(failure.type, failure.message)
      await loadItems()
    }
  })
}
function priceNumber(row) {
  const raw = String(row.raw?.price ?? row.price ?? '0').replace(/[¥￥,]/g, '').trim()
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : 0
}
function parseDraftMeta(item) {
  const text = item?.detailInfo || item?.detail_info || ''
  if (!text || typeof text !== 'string') return {}
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

async function publishDraft(row) {
  if (!ensureListAvailable('发布商品')) return
  const item = row.raw || row
  if (!item?.id) return
  const intentKey = String(item.id)
  let intent = publishDraftIntents[intentKey]
  const isNewIntent = !intent
  if (intent?.status === 'unknown') {
    return showNotice('error', '上次发布结果未知。请先同步商品或到闲鱼 App 核对；为避免重复发布，当前禁止重试。')
  }
  if (intent?.status === 'in_progress') {
    return showNotice('warn', '同一发布意图仍在执行，请勿重复提交。请稍后同步商品核对结果。')
  }

  if (!intent) {
    if (!query.xianyuAccountId && !item.accountId) return showNotice('warn', '请先选择发布账号')
    const image = item.imageUrl || item.coverPic || row.coverPic
    if (!image) return showNotice('warn', '发布前至少需要一张商品图片，请先补充图片')
    const price = priceNumber(row)
    if (!price) return showNotice('warn', '发布前需要设置有效价格')
    const meta = parseDraftMeta(item)
    const location = meta.location || item.location
    if (!location || !location.poiName) {
      return showNotice('warn', '发布前需要高德地图位置。请回到"商机发掘"草稿区搜索并选择发布位置，或在"发布商品"页重新发布。')
    }
    intent = {
      idempotencyKey: createExternalOperationKey('publish-draft'),
      status: 'pending',
      retrySafe: false,
      payload: {
        xianyuAccountId: Number(item.accountId || query.xianyuAccountId),
        localGoodsId: Number(item.id),
        title: String(item.title || row.name).slice(0, 30),
        description: item.description || item.title || row.name,
        imageUrls: [image],
        price,
        stock: Number(item.quantity || item.stock || 1) || 1,
        category: item.category && item.category !== '商机发掘' ? item.category : undefined,
        location,
      },
    }
    publishDraftIntents[intentKey] = intent
    saveExternalOperationIntents()
  }

  const onlyRepairLocal = intent.status === 'remote_confirmed'
  if (!await confirmAction({
    title: onlyRepairLocal ? '确认仅修复本地商品状态？' : `确认发布「${row.name}」？`,
    description: onlyRepairLocal
      ? '闲鱼平台已确认发布。本次只补全本地商品记录，不会再次调用发布接口。'
      : '发布前请确认标题、描述、图片、价格和位置真实有效。',
  })) {
    if (isNewIntent) clearExternalOperationIntent(publishDraftIntents, intentKey)
    return
  }
  return withItemBusy(row, async () => {
  try {
    await publishItem({
      ...intent.payload,
      idempotencyKey: intent.idempotencyKey,
    })
    clearExternalOperationIntent(publishDraftIntents, intentKey)
    showNotice('success', '发布成功，闲鱼平台与本地商品状态均已确认')
    await loadItems()
    loadGoodsStats()
  } catch(e) {
    const state = String(e?.data?.status || 'unknown')
    Object.assign(intent, {
      status: state,
      retrySafe: e?.data?.retrySafe === true,
      retryScope: e?.data?.retryScope || null,
    })
    saveExternalOperationIntents()
    if (state === 'remote_confirmed') {
      showNotice('warn', '闲鱼已确认发布，但本地状态未完成。再次点击发布只会修复本地记录，绝不会重复发布。')
    } else if (state === 'unknown') {
      showNotice('error', '发布结果未知。请先同步商品或到闲鱼 App 核对；当前禁止重试。')
    } else if (state === 'in_progress') {
      showNotice('warn', '同一发布意图正在执行，请勿重复提交。')
    } else {
      showNotice('error', e.message || '发布失败；平台明确失败时可安全重试原意图')
    }
  }
  })
}

/**
 * 统一删除商品：本地草稿由本地接口处理；已发布商品由服务端持久化
 * 状态机一次性负责平台删除与本地软删除，页面不拼接不可逆步骤。
 */
async function deleteProduct(row) {
  if (!ensureListAvailable('删除商品')) return
  if (isOffShelfBlockingOtherWrites(row)) return showNotice('warn', '下架流程尚未安全收尾，已阻止并发删除；请先完成本地状态或到闲鱼 App 核对。')
  const item = row.raw || row
  if (!item?.id) return
  const isLocalDraft = row.isLocalDraft
  const remoteDeleteState = row.remoteDeleteAttempt?.status

  const confirmDesc = isLocalDraft
    ? '该商品为本地草稿，删除后将从本地数据库移除。'
    : remoteDeleteState === 'remote_confirmed'
      ? '平台删除已经确认，本次只会安全重试本地软删除收尾，不会再次调用闲鱼删除。'
      : '服务端会依次确认平台删除与本地软删除。若平台结果未知，记录会保留并要求先到闲鱼 App 核对；该操作不可逆！'
  const confirmOptions = isLocalDraft
    ? { title: '确认删除该商品？', description: confirmDesc }
    : { title: '确认删除该商品？', description: confirmDesc, dangerous: true, confirmText: 'DELETE' }
  if (!await confirmAction(confirmOptions)) return

  return withItemBusy(row, async () => {
    try {
      if (isLocalDraft) {
        await deleteGoodsLocal(item.id)
        showNotice('success', '本地商品记录已删除')
      } else {
        const accountId = item.accountId || row.xianyuAccountId || Number(query.xianyuAccountId)
        if (!accountId) return showNotice('warn', '请先选择账号')
        const xyGoodsId = item.externalGoodsId || row.xyGoodId
        if (!xyGoodsId) return showNotice('warn', '缺少闲鱼商品ID')
        try {
          const response = await remoteDeleteItem({
            xianyuAccountId: accountId,
            xyGoodsId,
            idempotencyKey: remoteDeleteKey(item),
          })
          if (response?.data?.status !== 'confirmed') {
            return showNotice('warn', response?.data?.message || '删除尚未完成，请刷新状态后核对')
          }
          showNotice('success', '平台删除与本地软删除均已确认完成')
        } catch (e) {
          const failure = remoteDeleteFailure(e)
          showNotice(failure.type, failure.message)
          await loadItems()
          return
        }
      }
      await loadItems()
      loadGoodsStats()
    } catch (e) { showNotice('error', e.message || '删除失败') }
  })
}

/**
 * 批量删除商品：顺序逐个发起删除请求，复用现有单删端点。
 * - 本地草稿：直接 deleteGoodsLocal(item.id)
 * - 已发布商品：仅调用持久化远程删除状态机，不再由页面追加本地删除
 * 单个失败不影响后续，最终汇总成功/失败。
 */
async function batchDeleteProducts() {
  if (!ensureListAvailable('批量删除商品')) return
  if (!selectedKeys.value.length || batchDeleting.value) return
  // 找出选中行（基于 raw.id）
  const selectedRows = products.value.filter(p => selectedKeys.value.includes(p.raw?.id))
  if (!selectedRows.length) {
    showNotice('warn', '未找到选中的商品（可能已切换页面）')
    selectedKeys.value = []
    return
  }
  const blockedRows = selectedRows.filter(isOffShelfBlockingOtherWrites)
  if (blockedRows.length) {
    showNotice('warn', `${blockedRows.length} 件商品的下架流程尚未安全收尾，已阻止本次批量删除。请先逐件核对。`)
    return
  }

  const draftCount = selectedRows.filter(r => r.isLocalDraft).length
  const publishedCount = selectedRows.length - draftCount

  const desc = publishedCount > 0
    ? `选中 ${selectedRows.length} 件商品（已发布到闲鱼 ${publishedCount} 件，本地草稿 ${draftCount} 件）。已发布商品由服务端逐件确认平台删除与本地软删除；结果未知时不会自动重试。该操作不可逆！`
    : `选中 ${selectedRows.length} 件本地草稿商品，删除后将从本地数据库移除。`
  const confirmOptions = publishedCount > 0
    ? { title: '确认批量删除选中商品？', description: desc, dangerous: true, confirmText: 'DELETE' }
    : { title: '确认批量删除选中商品？', description: desc }
  if (!await confirmAction(confirmOptions)) return

  batchDeleting.value = true
  batchDeleteState.active = true
  batchDeleteState.done = 0
  batchDeleteState.total = selectedRows.length
  batchDeleteState.current = ''
  batchDeleteState.result = null

  const failed = []
  const warnings = []
  let success = 0

  for (const row of selectedRows) {
    const item = row.raw || row
    batchDeleteState.current = shortText(item.title || row.name, 20)
    try {
      if (row.isLocalDraft) {
        await deleteGoodsLocal(item.id)
        success++
      } else {
        const accountId = item.accountId || row.xianyuAccountId
        const xyGoodsId = item.externalGoodsId
        if (accountId && xyGoodsId) {
          try {
            const response = await remoteDeleteItem({
              xianyuAccountId: accountId,
              xyGoodsId,
              idempotencyKey: remoteDeleteKey(item),
            })
            const status = response?.data?.status
            if (status === 'confirmed') {
              success++
            } else if (status === 'remote_confirmed') {
              warnings.push({ name: row.name, reason: response?.data?.message || '平台已删除，本地收尾未完成' })
            } else {
              failed.push({ name: row.name, reason: response?.data?.message || '删除尚未确认完成' })
            }
          } catch (e) {
            const failure = remoteDeleteFailure(e)
            if (failure.type === 'warn') {
              warnings.push({ name: row.name, reason: failure.message })
            } else {
              failed.push({ name: row.name, reason: failure.message })
            }
          }
        } else {
          failed.push({ name: row.name, reason: '缺少账号或闲鱼商品ID' })
        }
      }
    } catch (e) {
      failed.push({ name: row.name, reason: e.message || '删除失败' })
    }
    batchDeleteState.done++
  }

  batchDeleteState.active = false
  batchDeleteState.current = ''
  batchDeleteState.result = { success, failed, warnings }
  batchDeleting.value = false
  selectedKeys.value = []

  if (failed.length === 0) {
    showNotice('success', `批量删除完成，共删除 ${success} 件商品`)
  } else {
    showNotice('warn', `批量删除完成：成功 ${success} / 失败 ${failed.length}，悬停"查看失败详情"查看`)
  }
  await loadItems()
  loadGoodsStats()
}
function normalizePriceInput(value) {
  const raw = String(value || '').replace('¥', '').trim()
  if (!/^\d+(\.\d{1,2})?$/.test(raw)) return ''
  const num = Number(raw)
  if (!Number.isFinite(num) || num <= 0 || num > 9999999) return ''
  return raw
}
async function editPrice(row) {
  if (!ensureListAvailable('修改商品价格')) return
  if (isOffShelfBlockingOtherWrites(row)) return showNotice('warn', '下架流程尚未安全收尾，已阻止并发改价；请先在闲鱼 App 核对。')
  const accountId = row.xianyuAccountId || Number(query.xianyuAccountId)
  if (!accountId) return showNotice('warn', '请先选择账号')
  const xyGoodsId = row.xyGoodId
  if (!xyGoodsId || String(xyGoodsId).startsWith('local:')) return showNotice('warn', '本地草稿不能远程改价')
  const intentKey = String(row.raw?.id || `${accountId}:${xyGoodsId}`)
  let intent = priceIntents[intentKey]
  if (intent?.status === 'unknown') {
    return showNotice('error', '上次改价结果未知。请先同步商品或到闲鱼 App 核对；为避免重复改价，当前禁止重试。')
  }
  if (intent?.status === 'in_progress') {
    return showNotice('warn', '同一改价意图仍在执行，请勿重复提交。请稍后同步商品核对结果。')
  }

  if (intent?.status === 'remote_confirmed') {
    const repair = await confirmAction({
      title: '确认仅修复本地价格？',
      description: `闲鱼平台已确认价格 ${intent.payload.price}。本次只补全本地商品状态，不会再次调用平台改价接口。`,
    })
    if (!repair) return
  } else {
    const input = await globalConfirm.prompt(
      '请输入新价格，最多两位小数',
      '',
      String(intent?.payload?.price || row.price).replace('¥',''),
    )
    if (input === false || input === null) return
    const price = normalizePriceInput(input)
    if (!price) return showNotice('warn', '价格必须大于 0、不超过 9999999，且最多两位小数')
    if (!intent || intent.payload?.price !== price || intent.retrySafe !== true) {
      intent = {
        idempotencyKey: createExternalOperationKey('update-price'),
        status: 'pending',
        retrySafe: false,
        payload: { xianyuAccountId: accountId, xyGoodsId, price },
      }
      priceIntents[intentKey] = intent
      saveExternalOperationIntents()
    }
  }

  return withItemBusy(row, async () => {
    try {
      await updateItemPrice({
        ...intent.payload,
        idempotencyKey: intent.idempotencyKey,
      })
      clearExternalOperationIntent(priceIntents, intentKey)
      showNotice('success', '商品价格已在闲鱼平台和本地确认')
      await loadItems()
    } catch (e) {
      const state = String(e?.data?.status || 'unknown')
      Object.assign(intent, {
        status: state,
        retrySafe: e?.data?.retrySafe === true,
        retryScope: e?.data?.retryScope || null,
      })
      saveExternalOperationIntents()
      if (state === 'remote_confirmed') {
        showNotice('warn', '闲鱼已确认改价，但本地价格未完成。再次点击改价只会修复本地状态。')
      } else if (state === 'unknown') {
        showNotice('error', '改价结果未知。请先同步商品或到闲鱼 App 核对；当前禁止重试。')
      } else if (state === 'in_progress') {
        showNotice('warn', '同一改价意图正在执行，请勿重复提交。')
      } else {
        showNotice('error', e.message || '改价失败；平台明确失败时可安全重试原意图')
      }
    }
  })
}
async function editStock(row) {
  if (!ensureListAvailable('修改商品库存')) return
  if (isOffShelfBlockingOtherWrites(row)) return showNotice('warn', '下架流程尚未安全收尾，已阻止并发库存修改；请先在闲鱼 App 核对。')
  const raw = await globalConfirm.prompt('请输入库存数量，必须为0或正整数', '', String(row.stock))
  if (raw === false || raw === null) return
  const normalized = String(raw).trim()
  if (!/^\d+$/.test(normalized) || Number(normalized) > 999999) return showNotice('warn', '库存必须为0到999999之间的整数')
  try { await updateGoods(row.raw.id, { stock: normalized, quantity: Number(normalized) }); showNotice('success', '库存更新成功'); await loadItems() } catch(e){ showNotice('error', e.message || '库存更新失败') }
}
async function loadDetail(row) { try { const res = await getGoodsDetail(row.raw?.id || row.id); selected.value = { ...row, raw: res.data || row.raw } } catch(e){ showNotice('error', e.message || '详情加载失败') } }
function onHeader(e){ if(e.detail === 'sync-products') syncProducts() }

// localStorage 键名常量
const LS_LAST_SYNC_TIME = 'xianyu_last_sync_time'
const LS_PENDING_SYNC = 'xianyu_pending_sync'
// 同步冷却期：3 小时（毫秒）
const SYNC_COOLDOWN_MS = 3 * 60 * 60 * 1000

async function autoTriggerSync() {
  // 自动触发同步：进入页面或切换账号时调用，不阻止用户操作
  if (!query.xianyuAccountId) {
    // 没有选中账号时正常加载已有数据
    loadItems()
    loadGoodsStats()
    return
  }

  // 检查是否有待同步标记（用户在其他页面发布了商品）
  const hasPendingSync = localStorage.getItem(LS_PENDING_SYNC) === 'true'

  if (!hasPendingSync) {
    // 检查冷却期：3 小时内同步过则跳过
    const lastSyncTime = localStorage.getItem(LS_LAST_SYNC_TIME)
    if (lastSyncTime) {
      const elapsed = Date.now() - Number(lastSyncTime)
      if (elapsed < SYNC_COOLDOWN_MS) {
        // 冷却期内：直接加载已有商品数据，不触发自动同步
        loadItems()
        loadGoodsStats()
        return
      }
    }
  }

  // 清除待同步标记
  localStorage.removeItem(LS_PENDING_SYNC)

  // 重置自动同步状态
  autoSyncState.active = true
  autoSyncState.completed = false
  autoSyncState.partial = false
  autoSyncState.error = ''
  autoSyncState.progress = 0
  autoSyncState.summary = { total: 0, new: 0, updated: 0, offShelf: 0, duration: 0 }
  // 清空原有商品数据，避免展示历史数据
  items.value = []
  totalCount.value = 0
  await syncProducts(true)
}

async function syncProducts(isAuto = false){
  if (!ensureListAvailable('提交商品同步')) return
  if (syncing.value) return
  // 未选账号（全部账号）：
  //   - 自动触发（isAuto=true）：进页面/切账号自动同步，不跑全账号（太重），仅加载已有数据
  //   - 手动点击按钮：顺序同步所有账号
  if(!query.xianyuAccountId) {
    if (isAuto) {
      loadItems()
      return
    }
    return syncAllAccounts()
  }
  // 已选账号：单账号同步（原有逻辑）
  clearNotice()
  syncing.value = true
  syncPollCanceled = false
  try {
    const res = await refreshItems({ xianyuAccountId: Number(query.xianyuAccountId) })
    const syncId = res.data?.syncId || res.data?.sync_id
    if (syncId) {
      syncTask.value = { id: syncId, status: 'running', progress: 0 }
      if (!isAuto) showNotice('info', '商品同步已启动，可继续使用页面；正在后台获取商品数据...')
      await pollSyncProgress(syncId, isAuto)
      await loadSyncTasks()
    } else {
      if (isAuto) {
        autoSyncState.active = false
        autoSyncState.completed = false
        autoSyncState.partial = false
        autoSyncState.error = '同步已提交但未返回可跟踪任务，结果暂无法确认；请稍后刷新任务历史。'
      }
      showNotice('info', '同步请求已提交，请稍后刷新商品列表')
    }
  } catch(e) {
    if (isAuto) {
      autoSyncState.active = false
      autoSyncState.completed = false
      autoSyncState.partial = false
      autoSyncState.error = e.message || '同步请求失败'
    }
    showNotice('error', e.message || '同步请求失败')
  }
  finally {
    if (!syncPollCanceled) {
      // 同步完成后重置到第1页
      query.pageNum = 1
      // 同步完成后，仅展示有效商品，排除已删除(status=3)的旧数据
      await loadItems({ excludeStatus: 3 })
      // 前端二次过滤：确保已删除(status=3)的商品不展示（兼容后端未更新excludeStatus的情况）
      // 注意：不覆盖 totalCount，loadItems 已从后端获取正确的总数
      items.value = items.value.filter(item => Number(item.status ?? 1) !== 3)
      await loadSyncTasks()
      loadGoodsStats()
    }
    syncing.value = false
  }
}

/**
 * 顺序同步所有账号：账号1完成后再同步账号2，避免并发调用闲鱼API触发风控。
 * 汇总各账号结果，单账号失败不影响后续账号。
 */
async function syncAllAccounts() {
  const accountList = accounts.value
  if (!accountList || !accountList.length) {
    showNotice('warn', '没有可同步的账号')
    return
  }
  if (syncing.value) return
  clearNotice()
  syncing.value = true
  syncPollCanceled = false

  autoSyncState.active = true
  autoSyncState.completed = false
  autoSyncState.partial = false
  autoSyncState.error = ''
  autoSyncState.progress = 0
  autoSyncState.summary = { total: 0, new: 0, updated: 0, offShelf: 0, duration: 0 }
  autoSyncState.accountIndex = 0
  autoSyncState.accountTotal = accountList.length
  autoSyncState.accountLabel = ''
  autoSyncState.failedAccounts = []
  // 清空原数据避免与同步过程混淆
  items.value = []
  totalCount.value = 0

  const totalSummary = { total: 0, new: 0, updated: 0, offShelf: 0, duration: 0 }

  try {
    const validAccounts = accountList.filter(acc => acc.deleted !== 1 && acc.status !== 0)
    for (let i = 0; i < validAccounts.length; i++) {
      if (syncPollCanceled) break
      const acc = validAccounts[i]
      const label = accountName(acc) || `账号 ${acc.id}`
      autoSyncState.accountIndex = i + 1
      autoSyncState.accountLabel = label
      // 不重置 progress 为 0，保留上一账号进度作为起点，避免进度回退闪烁
      try {
        const res = await refreshItems({ xianyuAccountId: Number(acc.id) })
        const syncId = res.data?.syncId || res.data?.sync_id
        if (syncId) {
          syncTask.value = { id: syncId, status: 'running', progress: 0 }
          // isAuto=false：让 pollSyncProgress 不直接更新 autoSyncState，由这里手动累加
          const summary = await pollSyncProgress(syncId, false)
          if (summary) {
            totalSummary.total += summary.total
            totalSummary.new += summary.new
            totalSummary.updated += summary.updated
            totalSummary.offShelf += summary.offShelf
            totalSummary.duration += summary.duration
          } else {
            autoSyncState.failedAccounts.push({ label, reason: '同步未完成或结果未知' })
          }
        } else {
          autoSyncState.failedAccounts.push({ label, reason: '未返回 syncId' })
        }
      } catch (e) {
        autoSyncState.failedAccounts.push({ label, reason: e.message || '同步失败' })
      }
    }

    autoSyncState.active = false
    autoSyncState.partial = autoSyncState.failedAccounts.length > 0
    autoSyncState.completed = !autoSyncState.partial
    autoSyncState.progress = 100
    autoSyncState.summary = totalSummary
    if (autoSyncState.failedAccounts.length > 0) {
      autoSyncState.error = `${autoSyncState.failedAccounts.length} 个账号同步失败：${autoSyncState.failedAccounts.map(f => f.label).join('、')}`
      showNotice('warn', `多账号同步部分完成：成功 ${accountList.length - autoSyncState.failedAccounts.length} / 失败 ${autoSyncState.failedAccounts.length}`)
    } else {
      autoSyncState.error = ''
      showNotice('success', `全部 ${accountList.length} 个账号同步完成`)
    }
    if (!autoSyncState.partial) {
      localStorage.setItem(LS_LAST_SYNC_TIME, String(Date.now()))
      localStorage.removeItem(LS_PENDING_SYNC)
    }
  } finally {
    if (!syncPollCanceled) {
      query.pageNum = 1
      await loadItems({ excludeStatus: 3 })
      // 注意：不覆盖 totalCount，loadItems 已从后端获取正确的总数
      items.value = items.value.filter(item => Number(item.status ?? 1) !== 3)
      await loadSyncTasks()
      loadGoodsStats()
    }
    syncing.value = false
  }
}

async function pollSyncProgress(syncId, isAuto = false) {
  let retries = 0
  let consecutiveQueryFailures = 0
  const maxRetries = 120
  const knownStatuses = ['queued', 'running', 'completed', 'failed', 'cancelled', 'not_found']
  while (retries < maxRetries && !syncPollCanceled) {
    await new Promise(r => setTimeout(r, 2000))
    if (syncPollCanceled) return null
    retries++
    let res
    try {
      res = await getSyncProgress(syncId)
      consecutiveQueryFailures = 0
    } catch (e) {
      consecutiveQueryFailures++
      if (consecutiveQueryFailures >= 3) {
        throw new Error(`同步状态连续查询失败：${e?.message || '服务不可用'}`)
      }
      if (retries % 5 === 0) showNotice('warn', '同步状态暂时不可用，仍在重试获取进度...')
      continue
    }
    const progress = res?.data
    if (!progress || typeof progress !== 'object' || Array.isArray(progress)) {
      throw new Error('同步进度响应格式异常')
    }
    const status = progress.status
    if (!knownStatuses.includes(status)) throw new Error('同步进度缺少有效任务状态')
    const pct = Number(progress.progress)
    if (!Number.isFinite(pct) || pct < 0 || pct > 100) throw new Error('同步进度数值异常')
    syncTask.value = { id: syncId, status, progress: pct }
    // 单账号自动同步场景下更新顶部横幅进度；多账号场景由 syncAllAccounts 自行管理
    if (isAuto) {
      autoSyncState.progress = pct
      if (progress.total) autoSyncState.summary.total = progress.total
      if (progress.new) autoSyncState.summary.new = progress.new
      if (progress.updated) autoSyncState.summary.updated = progress.updated
      if (progress.off_shelf) autoSyncState.summary.offShelf = progress.off_shelf
    }
    if (status === 'completed') {
      // 同步成功，更新最后同步时间戳
      localStorage.setItem(LS_LAST_SYNC_TIME, String(Date.now()))
      localStorage.removeItem(LS_PENDING_SYNC)
      const summary = {
        total: progress.total || 0,
        new: progress.new || 0,
        updated: progress.updated || 0,
        offShelf: progress.off_shelf || 0,
        duration: progress.duration_seconds || 0
      }
      const msg = `同步完成！共 ${summary.total} 件商品，新增 ${summary.new}，更新 ${summary.updated}，跳过 ${progress.skipped || 0}，下架 ${summary.offShelf}`
      if (isAuto) {
        autoSyncState.active = false
        autoSyncState.completed = true
        autoSyncState.partial = false
        autoSyncState.progress = 100
        autoSyncState.summary = summary
      }
      showNotice('success', msg)
      return summary
    }
    if (status === 'failed') {
      if (isAuto) {
        autoSyncState.active = false
        autoSyncState.completed = false
        autoSyncState.partial = false
        autoSyncState.error = progress.error || '同步失败'
      }
      showNotice('error', `同步失败: ${progress.error || '未知错误'}`)
      return null
    }
    if (status === 'cancelled') {
      throw new Error(progress.error || '同步任务已取消')
    }
    if (status === 'not_found') {
      throw new Error('同步任务不存在或已过期')
    }
    if (!isAuto) showNotice('info', `同步中... 进度 ${pct}%`)
  }
  if (!syncPollCanceled) {
    if (isAuto) {
      autoSyncState.active = false
      autoSyncState.completed = false
      autoSyncState.partial = false
      autoSyncState.error = '同步超时，请刷新页面查看结果'
    }
    showNotice('warn', '同步超时，请刷新页面查看结果')
  }
  return null
}
// 跳转到自动发货配置页面
const goToAutoDelivery = (row = null) => {
  const goodsId = row?.raw?.id ?? row?.id
  if (goodsId) {
    sessionStorage.setItem(AUTO_DELIVERY_FOCUS_GOODS_KEY, String(goodsId))
  }
  emit('navigate', 'auto-delivery')
}
onMounted(()=>{ restoreExternalOperationIntents(); void restoreItemPolish(); window.addEventListener('xya-header-action', onHeader); init() })
onBeforeUnmount(()=>{ syncPollCanceled = true; window.removeEventListener('xya-header-action', onHeader) })
</script>
<style scoped>
.polish-progress-banner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.polish-progress-banner > div {
  display: grid;
  gap: 4px;
}

.polish-progress-banner small {
  color: #667085;
}

.products-page {
  display: flex;
  gap: 16px;
  width: 100%;
  min-width: 0;
  /* 视口确定高度：让 .products-main 成为内部滚动容器，drawer 作为 flex 兄弟自然常驻可见。
     偏移 = main padding-top(22) + PageHeader(62) + main padding-bottom(20) = 104px */
  max-height: calc(100vh - 104px);
  min-height: 360px;
}
.products-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding-right: 4px;
}
.products-stat-grid {
  margin-bottom: 16px;
}
.products-table-card {
  min-width: 0;
}
.products-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 14px;
  flex-wrap: wrap;
}
.toolbar-filter {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}
.filter-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.toolbar-select {
  width: 140px;
  flex-shrink: 0;
}
.filter-search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 280px;
}
.products-search-input {
  flex: 1;
  min-width: 0;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.tabs.products-tabs {
  margin: 0;
  border-bottom: none;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: #f1f5fb;
  border-radius: 9px;
  padding: 3px;
}
.tabs.products-tabs .tab {
  border: none;
  border-radius: 7px;
  padding: 6px 14px;
  height: auto;
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
  background: transparent;
  transition: all 0.15s;
  white-space: nowrap;
}
.tabs.products-tabs .tab:hover {
  color: #1e40af;
  background: rgba(255,255,255,0.6);
}
.tabs.products-tabs .tab.active {
  color: #1d4ed8;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  font-weight: 600;
}

.table-scroll-wrap {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 10px;
}
.products-table {
  min-width: 1064px;
  table-layout: fixed;
}
.products-table :deep(th),
.products-table :deep(td) {
  white-space: nowrap;
}
.products-table :deep(th) {
  font-size: 13px;
  color: #64748b;
  font-weight: 600;
  background: #f8fafc;
}
.products-table :deep(th:nth-child(1)) { width: 44px; text-align: center; } /* 选择列 */
.products-table :deep(th:nth-child(2)) { width: 280px; text-align: left; }   /* 商品信息 */
.products-table :deep(th:nth-child(3)) { width: 80px; text-align: right; }    /* 价格 */
.products-table :deep(th:nth-child(4)) { width: 60px; text-align: center; }
.products-table :deep(th:nth-child(5)) { width: 60px; text-align: center; }
.products-table :deep(th:nth-child(6)) { width: 90px; text-align: center; }
.products-table :deep(th:nth-child(7)) { width: 110px; text-align: center; }
.products-table :deep(th:nth-child(8)) { width: 78px; text-align: center; }
.products-table :deep(th:nth-child(9)) { width: 78px; text-align: center; }
.products-table :deep(th:nth-child(10)) { width: 78px; text-align: center; }
.products-table :deep(th:nth-child(11)) { width: 140px; text-align: center; }
.products-table :deep(th:nth-child(12)) { width: 160px; text-align: center; }

.products-table :deep(td:nth-child(1)) { text-align: center; } /* 选择列 */
.products-table :deep(td:nth-child(2)) { text-align: left; }
.products-table :deep(td:nth-child(3)) { text-align: right; }
.products-table :deep(td:nth-child(4)),
.products-table :deep(td:nth-child(5)),
.products-table :deep(td:nth-child(6)),
.products-table :deep(td:nth-child(7)),
.products-table :deep(td:nth-child(8)),
.products-table :deep(td:nth-child(9)),
.products-table :deep(td:nth-child(10)),
.products-table :deep(td:nth-child(11)) { text-align: center; }
.products-table :deep(td:nth-child(12)) { text-align: center; }

.products-table :deep(tbody tr) { cursor: pointer; }
.products-table :deep(tbody tr.row-selected) { background: #eef5ff; box-shadow: inset 3px 0 0 #2563eb; }
.products-table :deep(tbody tr.row-selected:hover) { background: #e0edff; }
.products-table :deep(tbody tr:hover td) { background: #f5f9ff; }

.cell-center {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.cell-price {
  font-weight: 600;
  color: #ef4444;
  font-size: 14px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.cell-muted {
  color: #64748b;
  font-variant-numeric: tabular-nums;
}
.remote-delete-state {
  display: inline-block;
  margin-left: 6px;
  max-width: 104px;
  color: #b45309;
  font-size: 11px;
  line-height: 1.25;
  white-space: normal;
}
.remote-delete-state.state-unknown,
.remote-delete-state.state-failed {
  color: #b91c1c;
}

.op-buttons {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  justify-content: center;
}
.op-buttons .link {
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 13px;
  transition: background 0.15s;
}
.op-buttons .link:hover {
  background: #eef2ff;
}
.op-buttons .link.danger-text:hover {
  background: #fef2f2;
}
.op-buttons .link:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.product-cell {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  overflow: hidden;
}
.product-thumb {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  background: linear-gradient(135deg, #f5f7fb, #dfe9f8);
  border: 1px solid #eef2f7;
}
.product-thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
}
.product-info-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.product-info-text strong {
  font-size: 13.5px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 210px;
  line-height: 1.4;
}
.product-info-text em {
  font-size: 12px;
  color: #94a3b8;
  font-style: normal;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.delivery-type-configurable {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
  transition: background 0.15s;
  white-space: nowrap;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
}
.delivery-type-configurable:hover {
  background: rgba(255, 125, 0, 0.1);
}
.delivery-type-configurable .config-hint {
  font-size: 12px;
  color: #f59e0b;
  font-weight: 500;
  white-space: nowrap;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  font-size: 13px;
  color: #64748b;
  flex-wrap: wrap;
}
.products-pagination .pagination-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.page-size-label {
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
}
.page-size-select {
  width: 88px;
  height: 32px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fff;
  font-size: 13px;
  color: #1e293b;
  cursor: pointer;
}
.page-size-select:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12);
}
.page-size-unit {
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
}
.products-pagination .pagination-right {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.pagination-total {
  font-size: 13px;
  color: #64748b;
  margin-right: 8px;
  white-space: nowrap;
}
.page-no {
  min-width: 32px;
  height: 32px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.15s;
  user-select: none;
  background: #fff;
  border: 1px solid #e2e8f0;
  color: #475569;
}
.page-no:hover:not(:disabled) {
  background: #eef2ff;
  color: #2563eb;
  border-color: #c7d6f5;
}
.page-no.active {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}
.page-no:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  background: #f8fafc;
}
.page-ellipsis {
  min-width: 24px;
  text-align: center;
  color: #94a3b8;
  user-select: none;
}

@media (max-width: 768px) {
  .products-pagination {
    justify-content: center;
  }
}

.products-drawer {
  /* 高度跟随内容：align-self: flex-start 取消默认 stretch，底部贴合内容而非页面底部 */
  align-self: flex-start;
  /* 宽度由内容自适应，不固定 */
  width: fit-content;
  min-width: 300px;
  max-width: 380px;
  flex-shrink: 0;
  /* 常驻可见：.products-main 内部滚动（非 body 滚动），drawer 作为 flex 兄弟自然固定在右侧；
     内容过多时 drawer 内部滚动，不超出 .products-page 高度 */
  max-height: 100%;
  overflow-y: auto;
  background: #fff;
  border: 1px solid var(--line, #e5eaf2);
  border-radius: 14px;
  box-shadow: var(--shadow, 0 1px 3px rgba(0,0,0,0.04));
  padding: 16px;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.drawer-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}
.drawer-close {
  width: 30px;
  height: 30px;
  border: none;
  background: #f1f5f9;
  border-radius: 8px;
  font-size: 18px;
  cursor: pointer;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.drawer-close:hover {
  background: #e2e8f0;
  color: #1e293b;
}
.preview-card {
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 12px;
  border: 1px solid #eef2f7;
}
.drawer-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.5;
}
.drawer-price {
  margin: 0 0 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.drawer-card {
  margin-bottom: 12px;
}
.drawer-metrics {
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 14px;
}
.metric-tile {
  background: #f8fafc;
  border-radius: 10px;
  padding: 10px 8px;
  text-align: center;
  border: 1px solid #eef2f7;
}
.metric-tile span {
  font-size: 12px;
  color: #94a3b8;
  display: block;
}
.metric-tile b {
  font-size: 13px;
  margin-top: 4px;
  display: block;
  color: #1e293b;
}
.metric-tile b.text-green { color: #10b981; }
.metric-tile b.text-gray { color: #94a3b8; }
.drawer-actions {
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.drawer-actions :deep(button) {
  width: 100%;
}

.global-notice {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.products-table :deep(.badge.purple) {
  background: #f4efff;
  color: #7c3aed;
}

@media (max-width: 1280px) {
  .products-stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 1200px) {
  .products-drawer {
    min-width: 280px;
    max-width: 320px;
  }
}
@media (max-width: 1100px) {
  .toolbar-filter {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .filter-left {
    flex-wrap: wrap;
  }
  .filter-search {
    min-width: 0;
  }
}
@media (max-width: 900px) {
  .products-page {
    flex-direction: column;
    /* 移动端堆叠布局：取消视口高度限制，恢复内容高度 + body 滚动 */
    max-height: none;
    min-height: 0;
    gap: 12px;
  }
  .products-main {
    padding-right: 0;
  }
  .products-drawer {
    /* 移动端：恢复全宽自适应，不限制高度 */
    width: 100%;
    min-width: 0;
    max-width: none;
    max-height: none;
    padding: 12px;
  }
  .products-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 12px;
  }
  /* 工具栏：纵向堆叠，筛选/搜索/操作分行 */
  .products-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    margin-bottom: 10px;
  }
  .toolbar-filter {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .filter-left {
    flex-wrap: wrap;
    gap: 8px;
  }
  .toolbar-select {
    width: 100%;
  }
  .filter-search {
    min-width: 0;
    flex-wrap: wrap;
  }
  .products-search-input {
    min-width: 0;
    flex: 1 1 140px;
  }
  .toolbar-actions {
    flex-wrap: wrap;
    justify-content: flex-start;
    gap: 8px;
  }
  .tabs.products-tabs .tab {
    padding: 6px 10px;
    font-size: 12px;
  }
  /* 表格横向滚动（外层容器已设置，确保表格最小宽度触发挥滚动） */
  .table-scroll-wrap {
    -webkit-overflow-scrolling: touch;
  }
  .products-table {
    min-width: 900px;
  }
  /* 分页：左右两栏堆叠 */
  .products-pagination {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .products-pagination .pagination-left,
  .products-pagination .pagination-right {
    justify-content: center;
    flex-wrap: wrap;
  }
  .pagination-total {
    margin-right: 0;
    text-align: center;
    width: 100%;
  }
  .page-no {
    min-width: 36px;
    height: 36px;
  }
  /* 抽屉内指标与操作按钮：移动端保持 2 列以节省纵向空间 */
  .drawer-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
  }
  .metric-tile {
    padding: 8px 4px;
  }
  .metric-tile span {
    font-size: 11px;
  }
  .metric-tile b {
    font-size: 12px;
  }
  .drawer-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  /* 网格子元素防止溢出 */
  .products-stat-grid > *,
  .drawer-metrics > *,
  .drawer-actions > * {
    min-width: 0;
  }
  .drawer-header h3 {
    font-size: 15px;
  }
  .drawer-title {
    font-size: 14px;
  }
  /* 同步任务历史表格横向滚动 */
  :deep(.base-table) {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
  }
}
</style>
