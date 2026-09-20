import { API_BASE_URL, ApiError } from './client'
import type { SseEvent } from '../types'

interface ChatRequestBody {
  conversation_id: number
  message?: string
  confirm?: boolean
}

/**
 * 原生 EventSource 不支持自定义 header，没法带 `Authorization: Bearer`，
 * 所以用 fetch + ReadableStream 自己解析 SSE 帧（`event: x\ndata: y\n\n`）。
 */
export async function* streamChat(
  token: string,
  body: ChatRequestBody,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      signal,
    })
  } catch {
    throw new ApiError(0, '连不上服务器，请检查网络或后端是否在运行')
  }

  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* 响应体不是 JSON，就用 statusText */
    }
    throw new ApiError(res.status, detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const parsed = parseSseBlock(block)
      if (parsed) yield parsed
      boundary = buffer.indexOf('\n\n')
    }
  }
}

function parseSseBlock(block: string): SseEvent | null {
  const lines = block.split('\n')
  const eventLine = lines.find((l) => l.startsWith('event: '))
  const dataLine = lines.find((l) => l.startsWith('data: '))
  if (!eventLine || !dataLine) return null

  const event = eventLine.slice('event: '.length)
  const data = JSON.parse(dataLine.slice('data: '.length))
  return { event, data } as SseEvent
}
