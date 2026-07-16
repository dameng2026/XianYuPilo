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
  void record
  return false
}

export function canScheduleRedelivery(record) {
  void record
  return false
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
