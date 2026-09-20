import { apiJson } from './client'
import type { Conversation, TraceSpan } from '../types'

export function createConversation(token: string, title = '新对话'): Promise<Conversation> {
  return apiJson<Conversation>('/conversations', { method: 'POST', body: JSON.stringify({ title }) }, token)
}

export function listConversations(token: string): Promise<Conversation[]> {
  return apiJson<Conversation[]>('/conversations', { method: 'GET' }, token)
}

export function getConversationTrace(token: string, conversationId: number): Promise<TraceSpan[]> {
  return apiJson<TraceSpan[]>(`/conversations/${conversationId}/trace`, { method: 'GET' }, token)
}
