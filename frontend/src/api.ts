import type {
  Conversation,
  ConversationSummary,
  DocumentDetail,
  DocumentSummary,
  DonePayload,
  Health,
  Source,
  StreamHandlers,
  TraceStep,
} from './types'
import { API_BASE, jsonRequest, parseError, request } from './http'

export const api = {
  health: () => request<Health>('/health'),

  listConversations: () =>
    request<{ conversations: ConversationSummary[] }>('/conversations'),

  createConversation: (title?: string) =>
    jsonRequest<Conversation>('/conversations', 'POST', title ? { title } : {}),

  getConversation: (id: string) =>
    request<Conversation>(`/conversations/${encodeURIComponent(id)}`),

  renameConversation: (id: string, title: string) =>
    jsonRequest<{ id: string; title: string; updated_at: string }>(
      `/conversations/${encodeURIComponent(id)}`,
      'PATCH',
      { title },
    ),

  deleteConversation: (id: string) =>
    request<{ ok: boolean }>(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listDocuments: () => request<{ documents: DocumentSummary[] }>('/documents'),

  getDocument: (id: string) =>
    request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`),

  deleteDocument: (id: string) =>
    request<{ ok: boolean }>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentSummary>('/documents', { method: 'POST', body: form })
  },

  downloadDocumentUrl: (id: string) => `${API_BASE}/documents/${encodeURIComponent(id)}/download`,

  async streamChat(
    conversationId: string,
    content: string,
    handlers: StreamHandlers,
    signal: AbortSignal,
  ): Promise<void> {
    const response = await fetch(
      `${API_BASE}/conversations/${encodeURIComponent(conversationId)}/messages/stream`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
        signal,
      },
    )
    if (!response.ok) throw await parseError(response)
    if (!response.body) throw new Error('当前浏览器不支持流式响应')

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    const dispatch = (block: string) => {
      let event = 'message'
      const dataLines: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (!dataLines.length) return
      let data: unknown
      try {
        data = JSON.parse(dataLines.join('\n'))
      } catch {
        return
      }
      if (event === 'step') {
        handlers.onStep(data as TraceStep)
      } else if (event === 'sources') {
        handlers.onSources((data as { sources?: Source[] }).sources || [])
      } else if (event === 'delta') {
        handlers.onDelta((data as { content?: string }).content || '')
      } else if (event === 'done') {
        handlers.onDone(data as DonePayload)
      } else if (event === 'error') {
        throw new Error((data as { message?: string }).message || '生成失败，请重试')
      }
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
  },
}
