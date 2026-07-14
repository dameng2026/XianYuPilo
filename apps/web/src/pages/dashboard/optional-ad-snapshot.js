function toAdItems(data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.records)) return data.records
  if (Array.isArray(data?.list)) return data.list
  return []
}

export function resolveOptionalAdSnapshot(previousItems, settledResult) {
  const currentItems = Array.isArray(previousItems) ? previousItems : []
  if (settledResult?.status !== 'fulfilled') {
    return { items: currentItems, refreshed: false }
  }
  return {
    items: toAdItems(settledResult.value?.data),
    refreshed: true,
  }
}

export function buildOptionalAdUnavailableMessage(status, { hasSnapshot = false } = {}) {
  const serviceMessage = Number(status) === 503
    ? '广告商业服务未配置'
    : '无法确认广告商业服务可用'
  if (hasSnapshot) {
    return `${serviceMessage}；投放操作已禁用。已保留上次成功加载的广告快照，仅供浏览。`
  }
  return Number(status) === 503
    ? `${serviceMessage}；当前不展示占位广告，投放操作已禁用。`
    : `${serviceMessage}；当前不展示广告，投放操作已禁用。`
}
