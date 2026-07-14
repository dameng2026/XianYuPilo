<template>
  <AuthShell
    page-key="login"
    title-lead="让闲鱼运营"
    title-accent="更简单"
    title-tail="更高效"
    description="XianYuAssistant 开源版通过账号密码登录管理后台。"
    legal-description="该页面用于说明 XianYuAssistant 登录、身份验证与账号安全相关规则。"
    @navigate="emit('navigate', $event)"
  >
    <div v-if="errorMsg" class="form-error" role="alert" aria-live="assertive">{{ errorMsg }}</div>

    <form class="auth-form" @submit.prevent="handleLogin">
      <label class="auth-field" for="login-username">
        <TrustedSvg class="auth-field-icon" :markup="authIcons.user" />
        <span class="auth-sr-only">账号</span>
        <input
          id="login-username"
          v-model.trim="username"
          type="text"
          autocomplete="username"
          placeholder="请输入账号"
          required
          autofocus
        />
      </label>

      <div class="auth-field auth-field-with-action">
        <label class="auth-field-control" for="login-password">
          <TrustedSvg class="auth-field-icon" :markup="authIcons.lock" />
          <span class="auth-sr-only">密码</span>
          <input
            id="login-password"
            v-model="password"
            :type="showPwd ? 'text' : 'password'"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
          />
        </label>
        <button
          type="button"
          class="auth-eye-btn"
          :aria-label="showPwd ? '隐藏密码' : '显示密码'"
          :aria-pressed="showPwd"
          @click="showPwd = !showPwd"
        >
          <TrustedSvg :markup="showPwd ? authIcons.eyeOff : authIcons.eye" />
        </button>
      </div>

      <div class="auth-inline-row">
        <label class="auth-check">
          <input v-model="remember" type="checkbox" />
          <span>记住登录</span>
        </label>
      </div>

      <button class="auth-submit" type="submit" :disabled="!canSubmit" :aria-busy="loading">
        {{ loading ? '登录中...' : '登录' }}
      </button>
    </form>

    <div class="auth-agreement" role="note">
      当前部署尚未配置经审核的正式协议文本，登录不代表已完成知情同意。部署方商用前必须补齐
      <button type="button" class="auth-text-link" @click="openDoc('用户协议')">用户协议</button>
      和
      <button type="button" class="auth-text-link" @click="openDoc('隐私政策')">隐私政策</button>。
    </div>
  </AuthShell>
</template>

<script setup>
import { computed, ref } from 'vue'
import { login } from '../api/auth.js'
import AuthShell from '../components/auth/AuthShell.vue'
import TrustedSvg from '../components/TrustedSvg.vue'
import { authIcons, openLegalDoc } from '../components/auth/authContent.js'
import { friendlyError } from '../utils/friendlyError.js'

const emit = defineEmits(['navigate', 'login-success'])

const username = ref('')
const password = ref('')
const showPwd = ref(false)
const remember = ref(false)
const loading = ref(false)
const errorMsg = ref('')

const canSubmit = computed(() => Boolean(
  !loading.value &&
  username.value.trim() &&
  password.value
))

function openDoc(title) {
  openLegalDoc(title, '该页面用于说明 XianYuAssistant 登录、身份验证与账号安全相关规则。')
}

async function handleLogin() {
  if (loading.value) return
  errorMsg.value = ''

  if (!username.value.trim()) {
    errorMsg.value = '请输入账号'
    return
  }

  if (!password.value) {
    errorMsg.value = '请输入密码'
    return
  }

  loading.value = true
  try {
    const res = await login({
      username: username.value.trim(),
      password: password.value
    })
    emit('login-success', { ...(res.data || {}), remember: remember.value })
  } catch (error) {
    errorMsg.value = friendlyError(error, '登录失败，请检查账号、密码或网络状态')
  } finally {
    loading.value = false
  }
}
</script>
