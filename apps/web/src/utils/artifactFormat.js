/**
 * 工作流执行产物格式化工具
 *
 * 目标：将原本以 JSON 展示的节点产物转换为结构化文本，便于
 *   1) 用户在执行详情面板直接阅读
 *   2) 开发者复制文本用于排错
 *   3) 粘贴给 AI 助手定位失败环节
 *
 * 文本约定：
 *   - 首行固定为【标题】节点: xxx，便于快速识别环节
 *   - 第二行为摘要（数量/成功失败计数）
 *   - 之后逐条列出明细，成功用 ✓、失败用 ✗、跳过用 ⊘
 *   - 长字段做截断，避免单行过长
 */

function safeJsonParse(s) {
  if (s == null) return {}
  if (typeof s !== 'string') return s
  try { return JSON.parse(s) } catch { return { _raw: s } }
}

function trunc(s, n) {
  if (s == null) return ''
  s = String(s)
  return s.length > n ? s.slice(0, n) + '…' : s
}

function pick(obj, ...keys) {
  for (const k of keys) {
    if (obj[k] != null && obj[k] !== '') return obj[k]
  }
  return ''
}

/** 主入口：格式化单个产物为可读文本 */
export function formatArtifact(a) {
  if (!a) return ''
  const type = pick(a, 'artifactType', 'artifact_type') || 'json'
  const title = pick(a, 'title', 'artifactTitle') || type
  const nodeKey = pick(a, 'nodeKey', 'node_key') || ''
  const raw = a.content_json != null ? a.content_json : a.content
  const data = typeof raw === 'string' ? safeJsonParse(raw) : (raw || {})
  const header = `【${title}】 节点: ${nodeKey || '-'}`

  switch (type) {
    case 'goods':
      return formatGoods(header, data)
    case 'image':
      return formatImage(header, data)
    case 'text':
      return formatText(header, data)
    case 'publish_plan':
      return formatPublish(header, data)
    default:
      return formatGeneric(header, data)
  }
}

/** 商品获取 / 筛选后商品 */
function formatGoods(header, data) {
  const items = data.items || []
  const count = data.count != null ? data.count : items.length
  const keyword = data.keyword || ''
  const targetCount = data.targetCount
  const removed = data.removed
  const lines = [header]
  if (targetCount != null) {
    lines.push(`目标数量: ${targetCount} | 筛选后保留: ${items.length} | 移除: ${removed != null ? removed : '-'}`)
  } else {
    lines.push(`共获取 ${count} 个商品`)
  }
  if (keyword) lines.push(`关键词/店铺: ${keyword}`)
  items.forEach((it, i) => {
    lines.push('')
    lines.push(`[商品 ${i + 1}]`)
    lines.push(`  标题: ${trunc(it.title, 200)}`)
    lines.push(`  价格: ${it.price || '-'}`)
    lines.push(`  商品ID: ${pick(it, 'itemId', 'id') || '-'}`)
    if (it.link) lines.push(`  链接: ${trunc(it.link, 300)}`)
    if (it.seller) lines.push(`  卖家: ${it.seller}`)
    if (it.area) lines.push(`  地区: ${it.area}`)
    if (it.imageUrl) lines.push(`  图片: ${trunc(it.imageUrl, 300)}`)
    if (it.description) lines.push(`  描述: ${trunc(it.description, 300)}`)
    if (it.accountId != null) lines.push(`  账号: ${it.accountId}`)
  })
  if (!items.length) lines.push('（无商品）')
  return lines.join('\n')
}

/** 生成图片 + 生图后内联发布结果（新流程：每生成 1 张图立即发布） */
function formatImage(header, data) {
  const images = data.images || []
  const steps = data.steps || images
  const prompt = data.prompt || ''
  const allFailed = data.allFailed
  const okCount = (images.length ? images : steps).filter(i => i.aiOk).length
  const total = images.length || steps.length
  // ★ 发布结果（生图节点内联发布后产生）
  const publishResults = data.publishResults || []
  const pubSuccess = data.publishSuccessCount != null ? data.publishSuccessCount
    : publishResults.filter(r => r.status === 'published').length
  const pubFailed = data.publishFailedCount != null ? data.publishFailedCount
    : publishResults.filter(r => r.status === 'failed').length
  const pubSkippedAi = data.publishSkippedAiCount || publishResults.filter(r => r.status === 'skipped_no_ai_image').length
  const pubSkippedDup = data.publishSkippedDuplicateCount || publishResults.filter(r => r.status === 'skipped_duplicate').length

  const lines = [header]
  // ★ 摘要行：同时展示生图和发布统计
  let summary = `共 ${total} 张图 | 成功 ${okCount} / 失败 ${total - okCount}${allFailed ? ' (全部失败)' : ''}`
  if (publishResults.length > 0) {
    summary += `\n发布 ${publishResults.length} 个 | 成功 ${pubSuccess} / 失败 ${pubFailed} / 跳过(无AI图) ${pubSkippedAi} / 跳过(重复) ${pubSkippedDup}`
  }
  lines.push(summary)
  if (prompt) lines.push(`提示词: ${trunc(prompt, 300)}`)

  // ★ 逐张图详情，附带对应发布结果
  const list = images.length ? images : steps
  list.forEach((img, i) => {
    lines.push('')
    const ok = img.aiOk
    lines.push(`[图片 ${i + 1}] ${ok ? '✓ 生图成功' : '✗ 生图失败'}${img.accountId != null ? ' (账号 ' + img.accountId + ')' : ''}`)
    if (img.sourceTitle || img.title) lines.push(`  标题: ${trunc(img.sourceTitle || img.title, 200)}`)
    if (img.url || img.imgUrl) lines.push(`  封面图URL: ${trunc(img.url || img.imgUrl, 300)}`)
    if (img.aiReason) lines.push(`  AI原因: ${trunc(img.aiReason, 200)}`)
    if (img.sourceItemId) lines.push(`  来源商品: ${img.sourceItemId}`)
    if (!ok && img.error) lines.push(`  错误: ${trunc(img.error, 300)}`)

    // ★ 附加该图对应的发布结果
    const pub = publishResults[i]
    if (pub) {
      const pubLabel = pub.status === 'published' ? '✓ 发布成功'
        : pub.status === 'failed' ? '✗ 发布失败'
        : pub.status === 'skipped_no_ai_image' ? '⊘ 跳过(无AI图)'
        : pub.status === 'skipped_duplicate' ? '⊘ 跳过(重复)'
        : pub.status
      lines.push(`  发布结果: ${pubLabel}${pub.goods_id ? ' (商品ID: ' + pub.goods_id + ')' : ''}`)
      if (pub.category) lines.push(`  分类: ${trunc(pub.category, 100)}`)
      if (pub.addressText) lines.push(`  地址: ${trunc(pub.addressText, 100)}`)
      if (pub.error) lines.push(`  发布错误: ${trunc(pub.error, 300)}`)
      if (pub.publish_ms != null) lines.push(`  发布耗时: ${pub.publish_ms}ms`)
    }
  })
  if (!list.length) lines.push('（无图片）')
  return lines.join('\n')
}

/** 润色文案 */
function formatText(header, data) {
  const steps = data.steps || []
  const polished = data.polished || []
  const style = data.style || ''
  const marker = data.marker || ''
  const lines = [header]
  lines.push(`风格: ${style || '-'} | 共润色 ${steps.length} 条${marker ? ' | 标记: ' + marker : ''}`)
  steps.forEach((s, i) => {
    lines.push('')
    const ok = s.aiOk
    lines.push(`[润色 ${i + 1}] ${ok ? '✓ AI成功' : '✗ AI失败'} (账号 ${s.accountId ?? '-'}, 商品 ${s.itemId || '-'})`)
    if (s.aiReason) lines.push(`  AI原因: ${trunc(s.aiReason, 200)}`)
    if (s.aiSource) lines.push(`  AI来源: ${s.aiSource}`)
    if (s.sourceTitle) lines.push(`  源标题: ${trunc(s.sourceTitle, 200)}`)
    if (s.resultTitle) lines.push(`  结果标题: ${trunc(s.resultTitle, 200)}`)
    if (s.sourceDescPreview) lines.push(`  源描述: ${trunc(s.sourceDescPreview, 300)}`)
    if (s.resultDescPreview) lines.push(`  结果描述: ${trunc(s.resultDescPreview, 300)}`)
    if (s.aiResponsePreview) lines.push(`  AI响应: ${trunc(s.aiResponsePreview, 300)}`)
  })
  if (!steps.length && polished.length) {
    polished.forEach((p, i) => {
      lines.push('')
      lines.push(`[润色 ${i + 1}] (账号 ${p.accountId ?? '-'})`)
      if (p.title) lines.push(`  标题: ${trunc(p.title, 200)}`)
      if (p.description) lines.push(`  描述: ${trunc(p.description, 300)}`)
    })
  }
  if (!steps.length && !polished.length) lines.push('（无润色数据）')
  return lines.join('\n')
}

/** 发布计划 */
function formatPublish(header, data) {
  const results = data.publishResults || []
  const successCount = data.successCount != null ? data.successCount : results.filter(r => r.status === 'published').length
  const failedCount = data.failedCount != null ? data.failedCount : results.filter(r => r.status === 'failed').length
  const skippedAi = data.skippedNoAiCount || 0
  const skippedDup = data.skippedDuplicateCount || 0
  const lines = [header]
  lines.push(`成功 ${successCount} / 失败 ${failedCount} / 跳过(无AI图) ${skippedAi} / 跳过(重复) ${skippedDup}${data.dryRun ? ' | [试运行]' : ''}`)
  lines.push(`平台: ${data.platform || '-'} | 分类: ${data.category || '-'} | 主账号: ${data.account_id ?? '-'}`)
  if (data.address) {
    const addr = data.address
    const addrText = [addr.poiName, addr.area, addr.city, addr.prov].filter(Boolean).join(' ')
    if (addrText) lines.push(`地址: ${addrText}`)
  }
  results.forEach((r, i) => {
    lines.push('')
    const statusLabel = r.status === 'published' ? '✓ 已发布'
      : r.status === 'failed' ? '✗ 失败'
      : r.status === 'skipped_no_ai_image' ? '⊘ 跳过(无AI图)'
      : r.status === 'skipped_duplicate' ? '⊘ 跳过(重复)'
      : r.status
    lines.push(`[发布结果 ${i + 1}] ${statusLabel} (账号 ${r.account_id ?? '-'})`)
    if (r.title) lines.push(`  标题: ${trunc(r.title, 200)}`)
    if (r.goods_id) lines.push(`  发布商品ID: ${r.goods_id}`)
    if (r.image_url) lines.push(`  封面图: ${trunc(r.image_url, 300)}`)
    if (r.source_item_id) lines.push(`  来源商品: ${r.source_item_id}`)
    if (r.error) lines.push(`  错误: ${trunc(r.error, 300)}`)
    if (r.interval_seconds != null) lines.push(`  发布间隔: ${r.interval_seconds}秒`)
  })
  if (!results.length) lines.push('（无发布结果）')
  return lines.join('\n')
}

/** 兜底：触发器等未知类型 */
function formatGeneric(header, data) {
  const lines = [header]
  if (data && typeof data === 'object' && data.trigger) {
    const t = data.trigger
    lines.push(`执行次数: ${t.executeCount ?? '-'}`)
    if (t.selectedAccountIds && t.selectedAccountIds.length) {
      lines.push(`选中账号: ${t.selectedAccountId ?? '-'} (共 ${t.selectedAccountIds.length} 个: ${t.selectedAccountIds.join(', ')})`)
    } else if (t.selectedAccountId != null) {
      lines.push(`选中账号: ${t.selectedAccountId}`)
    }
    return lines.join('\n')
  }
  try {
    lines.push(JSON.stringify(data, null, 2))
  } catch {
    lines.push(String(data))
  }
  return lines.join('\n')
}

/** 格式化状态变量 */
export function formatStateVariable(v) {
  if (!v) return ''
  const type = pick(v, 'var_type', 'varType') || 'string'
  const name = pick(v, 'var_name', 'varName') || ''
  let value = v.var_value_parsed != null ? v.var_value_parsed : (v.var_value ?? '')
  if (typeof value === 'string' && value.trim().startsWith('{')) {
    try { value = JSON.parse(value) } catch { /* Keep the original string when it is not valid JSON. */ }
  }
  if (typeof value === 'object' && value !== null) {
    try { value = JSON.stringify(value, null, 2) } catch { /* Keep the original object representation. */ }
  }
  return `【${type}】 ${name}\n${value}`
}
