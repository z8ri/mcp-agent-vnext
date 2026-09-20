export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail || `请求失败（HTTP ${status}）`)
    this.status = status
    this.detail = detail
  }

  /** 给 ErrorBanner 用的粗分类——不是后端 ErrorCode 那一层，是 HTTP 语义这一层。 */
  get tier(): 'auth' | 'not_found' | 'rate_limited' | 'validation' | 'server' | 'network' {
    if (this.status === 401) return 'auth'
    if (this.status === 404) return 'not_found'
    if (this.status === 429) return 'rate_limited'
    if (this.status === 400 || this.status === 422) return 'validation'
    if (this.status === 0) return 'network'
    return 'server'
  }

  get retryable(): boolean {
    return this.tier === 'rate_limited' || this.tier === 'server' || this.tier === 'network'
  }

  toDisplayError(): import('../types').DisplayError {
    const titles: Record<ApiError['tier'], string> = {
      auth: '身份验证失败',
      not_found: '会话不存在',
      rate_limited: '请求太频繁',
      validation: '请求有误',
      server: '服务器出错',
      network: '网络连接失败',
    }
    return { title: titles[this.tier], message: this.detail || this.message, retryable: this.retryable }
  }
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.detail ?? JSON.stringify(body)
  } catch {
    return res.statusText
  }
}

export async function apiFetch(path: string, init: RequestInit = {}, token?: string | null): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, '连不上服务器，请检查网络或后端是否在运行')
  }

  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res))
  }
  return res
}

export async function apiJson<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const res = await apiFetch(path, init, token)
  return (await res.json()) as T
}
