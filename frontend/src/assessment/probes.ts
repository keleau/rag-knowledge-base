import type { AssessmentDetail } from './types'

const LEVEL_INDEX = { L1: 0, L2: 1, L3: 2, L4: 3 } as const

export interface Probe {
  index: string
  tag: string
  question: string
  reason: string
  status: string
  tone: 'gap' | 'watch' | 'covered'
}

export function buildProbes(data: AssessmentDetail): Probe[] {
  const cleanReason = (reason: string | undefined, tag: string): string => {
    const value = (reason || '').trim()
    if (!value) return ''
    return value.replace(tag, '').replace(/^[：:，,\s]+/, '').trim()
  }

  const capabilityProbe = (
    item: AssessmentDetail['capabilities'][number],
    position: number,
  ): Probe => {
    const current = item.current_level
    const target = item.target_level
    const met = current ? LEVEL_INDEX[current] >= LEVEL_INDEX[target] : false
    return {
      index: String(position).padStart(2, '0'),
      tag: item.tag,
      question: `面试官会怎么验证「${item.tag}」？`,
      reason:
        item.acceptance?.[0] ||
        item.evidence_quote ||
        `目标 ${target}，目前还没有形成可讲的项目证据。`,
      status: met ? `${current} / ${target}` : current ? `${current} → ${target}` : '待验证',
      tone: met ? 'covered' : current ? 'gap' : 'watch',
    }
  }

  const weakProbes = (data.weak_points ?? []).slice(0, 3).map((item, index) => ({
    index: String(index + 1).padStart(2, '0'),
    tag: item.tag,
    question: `面试官追问「${item.tag}」，你的证据是什么？`,
    reason: cleanReason(item.reason, item.tag) || '这项能力还没有讲清。',
    status: '证据缺口',
    tone: 'gap' as const,
  }))

  if (weakProbes.length >= 3) return weakProbes

  const usedTags = new Set(weakProbes.map((item) => item.tag))
  const capabilityProbes = (data.capabilities ?? [])
    .filter((item) => !usedTags.has(item.tag))
    .slice(0, 3 - weakProbes.length)
    .map((item, offset) => capabilityProbe(item, weakProbes.length + offset + 1))

  if (weakProbes.length + capabilityProbes.length) return [...weakProbes, ...capabilityProbes]

  return (data.tags ?? []).slice(0, 3).map((item, index) => ({
    index: String(index + 1).padStart(2, '0'),
    tag: item.name,
    question: `面试官可能会追问「${item.name}」的哪个细节？`,
    reason: item.description || '还没有形成这个能力的项目证据。',
    status: '待验证',
    tone: 'watch' as const,
  }))
}
