export const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '')

export async function parseError(response: Response): Promise<Error> {
  let message = `请求失败（HTTP ${response.status}）`
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') {
      message = body.detail
    } else if (Array.isArray(body?.detail)) {
      message = body.detail.map((item: { msg?: string }) => item.msg || '参数错误').join('；')
    } else if (typeof body?.message === 'string') {
      message = body.message
    }
  } catch {
    // keep the status-based fallback
  }
  return new Error(message)
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) throw await parseError(response)
  return (await response.json()) as T
}

export function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export function parseEventBlock(block: string): { event: string; data: unknown } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (!dataLines.length) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return null
  }
}

export interface SseHandlers {
  onEvent: (event: string, data: Record<string, unknown>) => void
}

/**
 * 读取一个 POST SSE 流。与现有聊天代码同一套解析，额外把每个事件交给 onEvent，
 * 由调用方按 event 名分发（stage / step / question / feedback / done / error）。
 */
export async function readSse(
  path: string,
  body: unknown,
  handlers: SseHandlers,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await parseError(response)
  if (!response.body) throw new Error('当前浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const dispatch = (block: string) => {
    const parsed = parseEventBlock(block)
    if (!parsed) return
    if (parsed.event === 'error') {
      const message = (parsed.data as { message?: string })?.message || '处理失败，请重试'
      throw new Error(message)
    }
    handlers.onEvent(parsed.event, (parsed.data || {}) as Record<string, unknown>)
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (value) buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        dispatch(block)
        boundary = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    if (buffer.trim()) dispatch(buffer)
  } finally {
    reader.releaseLock()
  }
}
