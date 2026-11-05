import type { Stage } from './types'

export type MissionKey = 'setup' | 'learning' | 'exam' | 'interview' | 'report'

export const MISSION_STAGES: Array<{ key: MissionKey; label: string }> = [
  { key: 'setup', label: '情报' },
  { key: 'learning', label: '演练' },
  { key: 'exam', label: '模拟考' },
  { key: 'interview', label: '实战' },
  { key: 'report', label: '复盘' },
]

export function missionForStage(value: Stage): MissionKey {
  if (value === 'learning') return 'learning'
  if (value === 'exam' || value === 'grading') return 'exam'
  if (value === 'interview') return 'interview'
  if (value === 'report' || value === 'practice' || value === 'done') return 'report'
  return 'setup'
}
