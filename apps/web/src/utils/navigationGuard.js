// 全局导航守卫注册表：离开受保护页面前，由注册的守卫函数决定是否放行
// 守卫函数返回 Promise<boolean>：true 放行，false 阻止（留在当前页）
let guardFn = null

export function setNavigationGuard(fn) {
  guardFn = typeof fn === 'function' ? fn : null
}

export function clearNavigationGuard() {
  guardFn = null
}

export async function runNavigationGuard() {
  if (typeof guardFn !== 'function') return true
  try {
    const result = await guardFn()
    return result !== false
  } catch {
    return true
  }
}
