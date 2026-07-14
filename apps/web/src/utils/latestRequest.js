/**
 * Creates a tiny generation gate for replace-style reads (lists, searches,
 * pagination). A request may only commit while it is still the newest one.
 */
export function createLatestRequestGuard() {
  let generation = 0

  return {
    begin() {
      const requestGeneration = ++generation
      const isCurrent = () => requestGeneration === generation

      return Object.freeze({
        isCurrent,
        commit(effect) {
          if (!isCurrent()) return false
          effect()
          return true
        },
      })
    },
    invalidate() {
      generation += 1
    },
  }
}

/**
 * Refreshes over an existing snapshot must not trigger the application-wide
 * blocking spinner or duplicate their page-local, non-blocking warning.
 */
export function listRefreshRequestConfig(hasSnapshot) {
  if (hasSnapshot === true) {
    return { uiMode: 'background', suppressGlobalError: true }
  }
  return { uiMode: 'foreground' }
}
