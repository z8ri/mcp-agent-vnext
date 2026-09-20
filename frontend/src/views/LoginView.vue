<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { ApiError } from '../api/client'
import ErrorBanner from '../components/ErrorBanner.vue'
import type { DisplayError } from '../types'

const email = ref('')
const password = ref('')
const mode = ref<'login' | 'register'>('login')
const error = ref<DisplayError | null>(null)
const submitting = ref(false)

const { login, register } = useAuth()
const router = useRouter()

async function submit() {
  submitting.value = true
  error.value = null
  try {
    if (mode.value === 'login') await login(email.value, password.value)
    else await register(email.value, password.value)
    router.push('/chat')
  } catch (e) {
    error.value = e instanceof ApiError ? e.toDisplayError() : { title: '未知错误', message: String(e), retryable: false }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <h1>MCP Agent vNext</h1>
      <p class="login-card__subtitle">{{ mode === 'login' ? '登录' : '注册一个新账号' }}</p>

      <label>
        邮箱
        <input v-model="email" type="email" required data-testid="email-input" />
      </label>
      <label>
        密码
        <input v-model="password" type="password" required minlength="8" data-testid="password-input" />
      </label>

      <ErrorBanner v-if="error" :error="error" @dismiss="error = null" @retry="submit" />

      <button type="submit" :disabled="submitting" data-testid="submit-button">
        {{ submitting ? '处理中…' : mode === 'login' ? '登录' : '注册' }}
      </button>

      <button type="button" class="login-card__switch" @click="mode = mode === 'login' ? 'register' : 'login'">
        {{ mode === 'login' ? '还没有账号？去注册' : '已经有账号？去登录' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f6fa;
}
.login-card {
  width: 320px;
  background: white;
  border-radius: 12px;
  padding: 28px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.login-card h1 {
  font-size: 18px;
  margin: 0;
}
.login-card__subtitle {
  margin: 0 0 8px;
  color: #666;
  font-size: 13px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #444;
}
input {
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}
button[type='submit'] {
  margin-top: 4px;
  padding: 9px;
  border: none;
  border-radius: 6px;
  background: #2f6fed;
  color: white;
  font-size: 14px;
  cursor: pointer;
}
button[type='submit']:disabled {
  opacity: 0.6;
  cursor: default;
}
.login-card__switch {
  border: none;
  background: transparent;
  color: #2f6fed;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
</style>
