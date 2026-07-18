import request from '../utils/request.js'

// 滑块求解涉及 Playwright 浏览器操作 + 多场景重试（加载转圈/点击重试/下载失败刷新），需 180 秒超时
const SOLVE_TIMEOUT = 180000

export const detectCaptcha = data => request.post('/captcha/detect', data)
export const getCaptchaInstructions = data => request.post('/captcha/instructions', data)
export const autoSolveCaptcha = data => request.post('/captcha/auto-solve', data, { timeout: SOLVE_TIMEOUT })
export const handleCaptcha = data => request.post('/captcha/handle', data, { timeout: SOLVE_TIMEOUT })
export const getCaptchaRecords = (params = {}) => request.get('/captcha/records', { params })
