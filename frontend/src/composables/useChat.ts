import { ref, type Ref } from 'vue'
import { streamChat } from '../api/chat'
import { ApiError } from '../api/client'
import { useAuth } from './useAuth'
import type { ConfirmRequiredPayload, DisplayError, SseEvent, TimelineEntry } from '../types'

function newId(): string {
  return crypto.randomUUID()
}

export function useChat(conversationId: Ref<number | null>) {
  const { token } = useAuth()
  const timeline = ref<TimelineEntry[]>([])
  const pendingConfirmation = ref<ConfirmRequiredPayload | null>(null)
  const error = ref<DisplayError | null>(null)
  const isStreaming = ref(false)
  let lastMessage: string | null = null

  function handleEvent(evt: SseEvent) {
    switch (evt.event) {
      case 'tool_call':
        timeline.value.push({ kind: 'tool_call', id: evt.data.id, tool: evt.data.tool, args: evt.data.args })
        break
      case 'tool_result': {
        const result = evt.data.result
        timeline.value.push({
          kind: 'tool_result',
          id: `${evt.data.tool_call_id}-result`,
          toolCallId: evt.data.tool_call_id,
          tool: evt.data.tool,
          ok: result.ok,
          summary: result.ok ? '执行成功' : (result.error?.message ?? '执行失败'),
        })
        break
      }
      case 'confirm_required':
        pendingConfirmation.value = evt.data
        break
      case 'message':
        timeline.value.push({ kind: 'assistant', id: newId(), content: evt.data.content })
        break
      case 'error':
        error.value = { title: '执行出错', message: evt.data.message, retryable: evt.data.retryable }
        break
      case 'final':
        break
    }
  }

  async function consume(generator: AsyncGenerator<SseEvent>) {
    isStreaming.value = true
    error.value = null
    try {
      for await (const evt of generator) handleEvent(evt)
    } catch (e) {
      error.value = e instanceof ApiError ? e.toDisplayError() : { title: '未知错误', message: String(e), retryable: true }
    } finally {
      isStreaming.value = false
    }
  }

  async function sendMessage(text: string) {
    if (conversationId.value == null || !token.value || !text.trim()) return
    timeline.value.push({ kind: 'user', id: newId(), content: text })
    lastMessage = text
    pendingConfirmation.value = null
    await consume(streamChat(token.value, { conversation_id: conversationId.value, message: text }))
  }

  async function confirmPending(approved: boolean) {
    if (conversationId.value == null || !token.value) return
    pendingConfirmation.value = null
    await consume(streamChat(token.value, { conversation_id: conversationId.value, confirm: approved }))
  }

  async function retry() {
    if (lastMessage) await sendMessage(lastMessage)
  }

  function reset() {
    timeline.value = []
    pendingConfirmation.value = null
    error.value = null
    lastMessage = null
  }

  return { timeline, pendingConfirmation, error, isStreaming, sendMessage, confirmPending, retry, reset }
}
