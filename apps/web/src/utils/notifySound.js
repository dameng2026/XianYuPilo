/**
 * 在线消息提示音工具
 * 基于 Web Audio API 生成悦耳的钟铃提示音，无需外部音频文件。
 * 仅在前端播放，与后端无关。
 */

let audioCtx = null

function getAudioContext() {
  if (typeof window === 'undefined') return null
  if (audioCtx) return audioCtx
  const AC = window.AudioContext || window.webkitAudioContext
  if (!AC) return null
  try {
    audioCtx = new AC()
  } catch {
    return null
  }
  return audioCtx
}

// 节流：连续收到多条消息时，避免提示音叠加播放
let lastPlayedAt = 0
const THROTTLE_MS = 2500

/**
 * 播放一个柔和的钟铃音色单音
 * @param {AudioContext} ctx
 * @param {number} freq 基频
 * @param {number} start 开始时间（相对 ctx.currentTime）
 * @param {number} duration 持续时间（秒）
 * @param {number} peak 主音峰值（0-1）
 */
function playBellTone(ctx, freq, start, duration, peak) {
  // 主音：正弦波
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(freq, start)
  gain.gain.setValueAtTime(0, start)
  gain.gain.linearRampToValueAtTime(peak, start + 0.008) // 8ms 柔和起音，避免咔哒声
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration) // 指数衰减，钟铃感
  osc.connect(gain).connect(ctx.destination)
  osc.start(start)
  osc.stop(start + duration + 0.05)

  // 谐波：2 倍频，增添钟铃色彩，音量很低
  const harmonic = ctx.createOscillator()
  const hGain = ctx.createGain()
  harmonic.type = 'sine'
  harmonic.frequency.setValueAtTime(freq * 2, start)
  hGain.gain.setValueAtTime(0, start)
  hGain.gain.linearRampToValueAtTime(peak * 0.22, start + 0.006)
  hGain.gain.exponentialRampToValueAtTime(0.0001, start + duration * 0.7)
  harmonic.connect(hGain).connect(ctx.destination)
  harmonic.start(start)
  harmonic.stop(start + duration * 0.7 + 0.05)
}

/**
 * 播放"收到对方消息"的提示音。
 * 上行纯五度双音（A5 → E6），钟铃音色，柔和悦耳。
 * 若浏览器尚未允许音频播放（如未发生用户手势），则静默跳过。
 */
export function playIncomingMessageSound() {
  const now = Date.now()
  if (now - lastPlayedAt < THROTTLE_MS) return
  lastPlayedAt = now

  const ctx = getAudioContext()
  if (!ctx) return

  // 浏览器自动播放策略：尝试恢复挂起的 AudioContext
  if (ctx.state === 'suspended') {
    ctx.resume().catch(() => {})
  }
  // 若仍未运行（无用户手势授权），静默跳过，不报错
  if (ctx.state !== 'running') return

  const t0 = ctx.currentTime
  // 第一音 A5 (880 Hz)
  playBellTone(ctx, 880.0, t0, 0.55, 0.16)
  // 第二音 E6 (1318.51 Hz) —— 纯五度上行，明亮悦耳
  playBellTone(ctx, 1318.51, t0 + 0.13, 0.65, 0.14)
}

/**
 * 在用户首次交互时预热 AudioContext，规避浏览器自动播放限制。
 * 应在应用启动时调用一次。
 */
let primed = false
export function primeAudioOnFirstGesture() {
  if (primed) return
  primed = true
  const resumeOnce = () => {
    const ctx = getAudioContext()
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().catch(() => {})
    }
    window.removeEventListener('pointerdown', resumeOnce)
    window.removeEventListener('keydown', resumeOnce)
  }
  window.addEventListener('pointerdown', resumeOnce, { passive: true })
  window.addEventListener('keydown', resumeOnce, { passive: true })
}
