import { dateTime } from './apiData.js'

const NUMERIC_STATUS_META = {
  0: { text: '待处理', badge: 'orange' },
  1: { text: '进行中', badge: 'blue' },
  2: { text: '成功', badge: 'green' },
  3: { text: '失败', badge: 'red' },
  4: { text: '已跳过', badge: 'gray' },
  5: { text: '等待买家', badge: 'orange' },
  6: { text: '缺货', badge: 'orange' },
  7: { text: '配置错误', badge: 'red' }
}

const STRING_STATUS_META = {
  pending: { text: '待处理', badge: 'orange' },
  running: { text: '进行中', badge: 'blue' },
  partial: { text: '部分成功', badge: 'orange' },
  message_sent: { text: '消息已发送，平台待确认', badge: 'orange' },
  success: { text: '成功', badge: 'green' },
  failed: { text: '失败', badge: 'red' },
  unknown: { text: '结果待人工核对', badge: 'orange' }
}

const TIMING_TEXT = {
  manual_immediate: '立即手动',
  after_payment: '付款后',
  after_receipt: '收货后',
  after_review: '评价后'
}

function deliveryStatusMeta(record) {
  const stringStatus = record?.deliveryStatus
  if (stringStatus) {
    return STRING_STATUS_META[String(stringStatus).toLowerCase()] || { text: String(stringStatus), badge: 'gray' }
  }
  return NUMERIC_STATUS_META[Number(record?.status)] || { text: String(record?.status ?? '-'), badge: 'gray' }
}

export function canRetryDeliveryRecord(record) {
  if (!record) return false
  // 仅文本模式支持重试（卡密模式需重新认领卡密，暂不支持）
  const mode = String(record?.deliveryMode || record?.delivery_mode || 'text').toLowerCase()
  if (mode !== 'text') return false
  // 必须有订单关联
  const orderId = Number(record?.orderId ?? record?.order_id ?? 0)
  if (!orderId) return false
  // 已成功记录不可重试
  const status = Number(record?.status ?? -1)
  if (status === 2) return false
  // 失败(3/6/7)、待处理(0/1/5) 可重试
  if ([0, 1, 3, 5, 6, 7].includes(status)) return true
  // 字符串状态兜底
  const deliveryStatus = String(record?.deliveryStatus || '').toLowerCase()
  if (['failed', 'pending', 'unknown'].includes(deliveryStatus)) return true
  return false
}

export function canScheduleRedelivery(record) {
  const numericStatus = Number(record?.status)
  const stringStatus = String(record?.deliveryStatus || '').toLowerCase()
  return [3, 6, 7].includes(numericStatus) || ['failed', 'partial'].includes(stringStatus)
}

export function buildDeliveryRecordRowViewModel(record) {
  const meta = deliveryStatusMeta(record)
  const quantityRequested = Number(record?.quantityRequested ?? 0) || 0
  const quantitySent = Number(record?.quantitySent ?? 0) || 0
  return {
    ...record,
    goodsTitleText: record?.goodsTitle || record?.goodsName || '-',
    goodsCoverPic: record?.goodsCoverPic || '',
    goodsId: record?.goodsId || null,
    externalOrderId: record?.externalOrderId || '',
    buyerNameText: record?.buyerNick || record?.buyerName || '-',
    sellerNameText: record?.sellerDisplayName || record?.sellerName || '-',
    purchaseTimeText: dateTime(record?.purchaseTime),
    timingText: TIMING_TEXT[record?.deliveryTiming || record?.timing] || record?.deliveryTiming || record?.timing || '-',
    deliveryModeText: record?.deliveryMode === 'card' ? '卡密' : '文本',
    deliveryStatusText: meta.text,
    deliveryBadge: meta.badge,
    deliveryProgressText: `${quantitySent} / ${quantityRequested}`,
    createdTimeText: dateTime(record?.createdTime),
    completedTimeText: dateTime(record?.completedTime || record?.finishedTime),
    platformSyncTimeText: dateTime(record?.platformSyncTime),
    canRetry: canRetryDeliveryRecord(record),
    canScheduleRedelivery: canScheduleRedelivery(record)
  }
}

export function buildDeliveryRecordDetailViewModel(record) {
  return {
    ...buildDeliveryRecordRowViewModel(record),
    deliveryContentText: record?.deliveryContent || record?.content || '-',
    resultText: record?.result || record?.deliveryResult || '-',
    errorMessageText: record?.errorMessage || '-'
  }
}
export function buildScheduleRedeliveryPayload(form) {
  return {
    cronExpression: String(form?.cronExpression || '').trim()
  }
}
