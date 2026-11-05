import { jsonRequest, readSse, request } from '../http'
import type {
  AssessmentDetail,
  Capability,
  ExamAnswer,
  ExamQuestion,
  PracticeItem,
  Project,
  ProjectCode,
  Report,
  Session,
} from './types'

const base = '/assessments'

function qs(version?: number | null): string {
  return version === null || version === undefined ? '' : `?version=${version}`
}

export const assessmentApi = {
  list: () => request<{ assessments: Session[] }>(base),
  create: (title?: string) => jsonRequest<Session>(base, 'POST', title ? { title } : {}),
  get: (id: string) => request<AssessmentDetail>(`${base}/${encodeURIComponent(id)}`),
  remove: (id: string) => request<{ ok: boolean }>(`${base}/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  uploadResume: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ document: { id: string; name: string; chunk_count: number } }>(
      `${base}/${encodeURIComponent(id)}/resume`,
      { method: 'POST', body: form },
    )
  },

  extractProjects: (id: string, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) =>
    readSse(`${base}/${encodeURIComponent(id)}/extract-projects`, undefined, { onEvent }, signal),

  listProjects: (id: string) => request<{ projects: Project[] }>(`${base}/${encodeURIComponent(id)}/projects`),

  patchProject: (projectId: string, patch: Partial<Project>) =>
    jsonRequest<Project>(`/projects/${encodeURIComponent(projectId)}`, 'PATCH', patch),

  selectProject: (id: string, projectId: string) =>
    jsonRequest<{ ok: boolean }>(`${base}/${encodeURIComponent(id)}/project`, 'POST', { project_id: projectId }),

  uploadProjectDocument: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ document: { id: string; name: string; chunk_count: number } }>(
      `${base}/${encodeURIComponent(id)}/project-document`,
      { method: 'POST', body: form },
    )
  },

  uploadCode: (id: string, fileName: string, content: string) =>
    jsonRequest<{ code: ProjectCode; symbol_count: number; symbols: ProjectCode['symbols'] }>(
      `${base}/${encodeURIComponent(id)}/code`,
      'POST',
      { file_name: fileName, content },
    ),

  deleteCode: (id: string) => request<{ ok: boolean }>(`${base}/${encodeURIComponent(id)}/code`, { method: 'DELETE' }),

  listEntities: (id: string) => request<{ entities: AssessmentDetail['entities'] }>(`${base}/${encodeURIComponent(id)}/entities`),

  prepare: (id: string, version: number, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) =>
    readSse(`${base}/${encodeURIComponent(id)}/prepare${qs(version)}`, undefined, { onEvent }, signal),

  listCapabilities: (id: string) => request<{ capabilities: Capability[] }>(`${base}/${encodeURIComponent(id)}/capabilities`),

  patchCapability: (capabilityId: string, targetLevel: string) =>
    jsonRequest<Capability>(`/capabilities/${encodeURIComponent(capabilityId)}`, 'PATCH', { target_level: targetLevel }),

  listPractice: (id: string, cycle = 0) =>
    request<{ cycle: number; items: PracticeItem[] }>(`${base}/${encodeURIComponent(id)}/practice?cycle=${cycle}`),

  answerPractice: (itemId: string, content: string, selfScore: number | null) =>
    jsonRequest<{ ok: boolean }>(`/practice-items/${encodeURIComponent(itemId)}/answer`, 'POST', {
      content,
      self_score: selfScore,
    }),

  morePractice: (id: string, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) =>
    readSse(`${base}/${encodeURIComponent(id)}/practice/more`, undefined, { onEvent }, signal),

  startExam: (id: string, version: number | null, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) =>
    readSse(`${base}/${encodeURIComponent(id)}/exam/start${qs(version)}`, undefined, { onEvent }, signal),

  getExam: (id: string) => request<{ questions: ExamQuestion[] }>(`${base}/${encodeURIComponent(id)}/exam`),

  submitExam: (
    id: string,
    version: number | null,
    answers: Array<{ question_id: string; content: string }>,
    idempotencyKey: string,
    skipExam = false,
  ) =>
    jsonRequest<{ stage: string; version: number; next_action: string }>(
      `${base}/${encodeURIComponent(id)}/exam/submit${qs(version)}`,
      'POST',
      { idempotency_key: idempotencyKey, answers, skip_exam: skipExam },
    ),

  gradeExam: (id: string, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) =>
    readSse(`${base}/${encodeURIComponent(id)}/exam/grade`, undefined, { onEvent }, signal),

  weakPoints: (id: string) => request<{ weak_points: AssessmentDetail['weak_points'] }>(`${base}/${encodeURIComponent(id)}/weak-points`),

  startInterview: (id: string, version: number | null) =>
    jsonRequest<{ turn: AssessmentDetail['interview']['turns'][number]; turns: AssessmentDetail['interview']['turns'] }>(
      `${base}/${encodeURIComponent(id)}/interview/start${qs(version)}`,
      'POST',
    ),

  answerInterview: (id: string, content: string, version: number | null) =>
    jsonRequest<{
      grade: { score: number; hits: ExamAnswer['hits']; needs_review: boolean }
      finished: boolean
      turns: AssessmentDetail['interview']['turns']
      current_round: number
      version: number
    }>(`${base}/${encodeURIComponent(id)}/interview/answer${qs(version)}`, 'POST', { content }),

  getInterview: (id: string) => request<{ turns: AssessmentDetail['interview']['turns'] }>(`${base}/${encodeURIComponent(id)}/interview`),

  makeReport: (id: string, version: number | null, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) =>
    readSse(`${base}/${encodeURIComponent(id)}/report${qs(version)}`, undefined, { onEvent }, signal),

  getReport: (id: string) => request<{ report: Report }>(`${base}/${encodeURIComponent(id)}/report`),

  startRepeat: (id: string, version: number | null, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) =>
    readSse(`${base}/${encodeURIComponent(id)}/repeat/start${qs(version)}`, undefined, { onEvent }, signal),

  submitRepeat: (
    id: string,
    version: number | null,
    answers: Array<{ question_id: string; content: string }>,
  ) =>
    jsonRequest<{ answered: number; evaluation: Record<string, unknown>; stage: string; version: number }>(
      `${base}/${encodeURIComponent(id)}/repeat/submit${qs(version)}`,
      'POST',
      { answers },
    ),

  getRepeat: (id: string) => request<{ cycle: number; items: PracticeItem[]; evaluation: Record<string, unknown> }>(`${base}/${encodeURIComponent(id)}/repeat`),

  advance: (id: string, toStage: string, version: number | null) =>
    jsonRequest<{ stage: string; version: number }>(`${base}/${encodeURIComponent(id)}/advance`, 'POST', {
      to_stage: toStage,
      version,
    }),

  getCodeContent: (id: string) =>
    request<{ content: string | null; file_name: string | null }>(`${base}/${encodeURIComponent(id)}/code/content`),
}
