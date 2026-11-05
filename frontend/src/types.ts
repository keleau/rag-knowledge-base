export interface Source {
  document_id: string
  document_name: string
  chunk_id: string
  chunk_index: number
  text: string
  score?: number
}

export interface TraceStep {
  id: string
  name: string
  label: string
  status: 'done' | 'error' | 'running'
  summary: string
  duration_ms?: number
  result_count?: number | null
  args?: Record<string, unknown>
  kind?: 'tool' | 'check'
}

export interface Usage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sources?: Source[]
  trace?: TraceStep[]
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  preview: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: Message[]
}

export interface DocumentSummary {
  id: string
  name: string
  size: number
  chunk_count: number
  char_count: number
  created_at: string
  updated_at: string
}

export interface DocumentChunk {
  id: string
  index: number
  text: string
}

export interface DocumentDetail extends DocumentSummary {
  chunks: DocumentChunk[]
}

export interface Health {
  status: string
  app: string
  demo_mode: boolean
  llm_mode?: string
  model: string
  chunk_size: number
  chunk_overlap: number
  top_k: number
  max_upload_mb: number
  documents: number
  chunks: number
  characters: number
  agent_max_steps?: number
  agent_max_contexts?: number
}

export interface DonePayload {
  conversation_id: string
  message_id: string
  title: string
  content: string
  trace?: TraceStep[]
  usage?: Usage
}

export interface StreamHandlers {
  onStep: (step: TraceStep) => void
  onSources: (sources: Source[]) => void
  onDelta: (delta: string) => void
  onDone: (payload: DonePayload) => void
}

export type ToastKind = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  kind: ToastKind
  message: string
}
