export function difficultyLabel(value: string): string {
  return { easy: '简单', medium: '中等', hard: '困难' }[value] || value
}

export function codeModeLabel(value: string | null | undefined): string {
  return { locate: '定位题', explain: '讲解题', implement: '实现题' }[value || ''] || ''
}

export function levelLabel(value: string | null | undefined): string {
  return { L1: 'L1 知道', L2: 'L2 解释', L3: 'L3 迁移', L4: 'L4 讲清' }[value || ''] || '未覆盖'
}

export function newIdempotencyKey(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}
