export interface Conversation {
  id: number
  title: string
  created_at: string
}

export interface ToolCallPayload {
  tool: string
  args: Record<string, unknown>
  id: string
}

export interface ToolResultPayload {
  tool_call_id: string
  tool: string
  result: {
    ok: boolean
    server?: string
    tool?: string
    data?: unknown
    error?: { code: string; message: string; retryable: boolean }
  }
}

export interface ConfirmRequiredPayload {
  type: 'confirm_tool_call'
  tool: string
  args: Record<string, unknown>
  tool_call_id: string
}

export interface MessagePayload {
  content: string
}

export interface ErrorPayload {
  code: string
  message: string
  retryable: boolean
}

export type SseEvent =
  | { event: 'tool_call'; data: ToolCallPayload }
  | { event: 'tool_result'; data: ToolResultPayload }
  | { event: 'confirm_required'; data: ConfirmRequiredPayload }
  | { event: 'message'; data: MessagePayload }
  | { event: 'final'; data: Record<string, never> }
  | { event: 'error'; data: ErrorPayload }

// 时间线上展示的条目，跟后端 SSE 事件不是一一对应——一条 assistant 消息、
// 一次工具调用、一次工具结果分别是独立的条目，方便前端各自渲染。
export type TimelineEntry =
  | { kind: 'user'; id: string; content: string }
  | { kind: 'assistant'; id: string; content: string }
  | { kind: 'tool_call'; id: string; tool: string; args: Record<string, unknown> }
  | { kind: 'tool_result'; id: string; toolCallId: string; tool: string; ok: boolean; summary: string }

export interface DisplayError {
  title: string
  message: string
  retryable: boolean
}

export interface TraceSpan {
  span_id: string
  parent_span_id: string | null
  name: string
  status: 'ok' | 'error'
  started_at: number
  duration_ms: number
  attributes: Record<string, unknown>
}
