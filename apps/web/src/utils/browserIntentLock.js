export async function withBrowserIntentLock(name, task) {
  const requestLock = globalThis.navigator?.locks?.request
  if (typeof requestLock !== 'function') {
    throw new Error('当前浏览器不支持跨标签页写入锁，已禁止外部写操作。请使用受支持的最新版浏览器。')
  }
  return requestLock.call(globalThis.navigator.locks, `xya:${name}`, { mode: 'exclusive' }, task)
}
