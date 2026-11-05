export type Stage = 'setup' | 'learning' | 'exam' | 'grading' | 'interview' | 'report' | 'practice' | 'done'

export interface Session {
  id: string
  title: string
  stage: Stage
  status: string
  version: number
  current_round: number
  practice_cycle: number
  passed: number
  resume_document_id: string | null
  project_id: string | null
  project_document_id: string | null
  project_code_id: string | null
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  name: string
  role: string | null
  period: string | null
  summary: string | null
  source_quote: string
  selected: number
}

export interface Tag {
  id: string
  name: string
  description: string
}

export interface Capability {
  id: string
  tag_id: string
  tag: string
  target_level: 'L1' | 'L2' | 'L3' | 'L4'
  current_level: 'L1' | 'L2' | 'L3' | 'L4' | null
  acceptance: string[]
  evidence_quote: string
  met: number
}

export interface Entity {
  id: string
  name: string
  kind: string
  source_type: 'project_doc' | 'code'
}

export interface CodeSymbol {
  name: string
  kind: string
  line: number
  end_line: number
}

export interface ProjectCode {
  id: string
  file_name: string
  language: string
  line_count: number
  symbols: CodeSymbol[]
}

export interface PracticeItem {
  id: string
  tag_id: string
  tag: string
  kind: 'card' | 'question' | 'code_question'
  cycle: number
  prompt: string
  answer: string | null
  explanation: string | null
  source_quote: string | null
  source_file: string | null
  line_start: number | null
  line_end: number | null
  code_mode: 'locate' | 'explain' | 'implement' | null
  symbols: string[]
  entities: string[]
  difficulty: 'easy' | 'medium' | 'hard'
  user_answer: string | null
  self_score: number | null
}

export interface ExamQuestion {
  id: string
  tag_id: string
  tag: string
  type: 'single_choice' | 'short_answer' | 'code'
  code_mode: 'locate' | 'explain' | 'implement' | null
  prompt: string
  options: string[]
  difficulty: string
  source_quote: string | null
  source_file: string | null
  line_start: number | null
  line_end: number | null
  symbols: string[]
}

export interface ExamAnswer {
  question_id: string
  content: string
  score: number | null
  max_score: number | null
  hits: Array<{ point?: string; hit?: boolean; kind?: string; evidence?: string; weight?: number }>
  evidence: Array<Record<string, unknown>>
  needs_review: boolean
  review_note: string | null
}

export interface WeakPoint {
  id: string
  tag_id: string
  tag: string
  severity: number
  reason: string
  evidence: Array<Record<string, unknown>>
}

export interface InterviewTurn {
  id: string
  tag_id: string
  tag: string
  round_index: number
  question: string
  answer: string | null
  rubric: Array<{ point?: string; weight?: number }>
  score: number | null
  evidence: Array<{ point?: string; hit?: boolean }>
  status: 'asking' | 'answered' | 'graded'
  follow_up_of: string | null
}

export interface ReportCapability {
  tag_id: string
  tag: string
  target: string
  current: string | null
  met: boolean
  covered: boolean
  gap: string
}

export interface Report {
  passed: boolean
  level: string | null
  summary: string
  capabilities: ReportCapability[]
  tags: Array<{ tag: string; practice: number; exam: number; interview: number | null }>
  strengths: string[]
  weaknesses: Array<{ tag: string; reason: string; evidence: Array<Record<string, unknown>> }>
  actions: string[]
  next: string[]
}

export interface AssessmentDetail {
  session: Session
  projects: Project[]
  selected_project: Project | null
  tags: Tag[]
  capabilities: Capability[]
  entities: Entity[]
  code: ProjectCode | null
  practice: { cycle: number; items: PracticeItem[]; count: number; is_review: boolean }
  exam: { started: boolean; questions: ExamQuestion[]; answers: ExamAnswer[] }
  weak_points: WeakPoint[]
  interview: { turns: InterviewTurn[]; current_round: number }
  report: Report | null
  next_action: string
  llm_mode: string
}

export type StreamEvent =
  | { event: 'step'; data: { label: string; summary: string; status?: string; rejected?: Array<{ prompt: string; reason: string }> } }
  | { event: 'stage'; data: { stage: string; status: string } }
  | { event: 'question'; data: { question: string } }
  | { event: 'feedback'; data: Record<string, unknown> }
  | { event: 'done'; data: Record<string, unknown> }
