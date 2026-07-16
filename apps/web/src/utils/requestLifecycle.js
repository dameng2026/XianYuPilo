export function createRequestGate() {
  let generation = 0
  let active = true

  return {
    begin() {
      generation += 1
      return generation
    },

    isCurrent(requestGeneration) {
      return active && requestGeneration === generation
    },

    invalidate() {
      generation += 1
    },

    dispose() {
      active = false
      generation += 1
    },
  }
}
