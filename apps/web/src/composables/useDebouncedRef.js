import { ref, watch, onBeforeUnmount } from 'vue'

/**
 * 创建一个防抖 ref：源 ref 变化后延迟 ms 毫秒同步到目标 ref。
 * 用于搜索框输入等场景，避免每次按键都触发昂贵的计算。
 *
 * @param {import('vue').Ref} source 源 ref（通常绑定到 v-model）
 * @param {number} ms 防抖延迟（毫秒），默认 300
 * @returns {import('vue').Ref} 防抖后的 ref
 */
export function useDebouncedRef(source, ms = 300) {
  const debounced = ref(source.value)
  let timer = null
  watch(source, (val) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      debounced.value = val
      timer = null
    }, ms)
  })
  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
  })
  return debounced
}
