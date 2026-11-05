import type { AssessmentDetail } from './types'

export interface AbilityStat {
  id: string
  name: string
  total: number
  done: number
  percent: number
  average: number | null
  target: string
}

export function buildAbilityStats(detail: AssessmentDetail): AbilityStat[] {
  const questions = detail.practice.items.filter((item) => item.kind !== 'card')
  return detail.tags.map((tag) => {
    const items = questions.filter((item) => item.tag_id === tag.id)
    const done = items.filter((item) => item.user_answer).length
    const scored = items.filter((item) => typeof item.self_score === 'number')
    const average = scored.length
      ? Math.round(scored.reduce((sum, item) => sum + (item.self_score || 0), 0) / scored.length)
      : null
    const capability = detail.capabilities.find((item) => item.tag_id === tag.id)
    return {
      id: tag.id,
      name: tag.name,
      total: items.length,
      done,
      percent: items.length ? Math.round((done / items.length) * 100) : 0,
      average,
      target: capability?.target_level || 'L2',
    }
  })
}
