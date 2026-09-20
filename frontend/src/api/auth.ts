import { apiJson } from './client'

export interface TokenResponse {
  access_token: string
  token_type: string
}

export function register(email: string, password: string): Promise<TokenResponse> {
  return apiJson<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiJson<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}
