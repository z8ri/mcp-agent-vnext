import { ref } from 'vue'
import * as authApi from '../api/auth'

const STORAGE_KEY = 'mcp-agent-vnext.token'

const token = ref<string | null>(localStorage.getItem(STORAGE_KEY))

function setToken(value: string | null) {
  token.value = value
  if (value) localStorage.setItem(STORAGE_KEY, value)
  else localStorage.removeItem(STORAGE_KEY)
}

export function useAuth() {
  async function login(email: string, password: string) {
    const res = await authApi.login(email, password)
    setToken(res.access_token)
  }

  async function register(email: string, password: string) {
    const res = await authApi.register(email, password)
    setToken(res.access_token)
  }

  function logout() {
    setToken(null)
  }

  return { token, login, register, logout, isAuthenticated: () => token.value !== null }
}
