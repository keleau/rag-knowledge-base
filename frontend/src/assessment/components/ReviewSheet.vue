<script setup lang="ts">
import { computed } from 'vue'
import type { Report } from '../types'
import { levelLabel } from '../ui'

const props = defineProps<{
  report: Report
  projectName: string
  reviewDate: string
}>()

const emit = defineEmits<{
  (event: 'repeat'): void
  (event: 'print'): void
}>()

const weaknesses = computed(() => {
  if (props.report.weaknesses?.length) return props.report.weaknesses
  return props.report.capabilities
    .filter((item) => !item.met)
    .map((item) => ({
      tag: item.tag,
      reason: item.gap || '还没有达到目标。',
      evidence: [] as Array<Record<string, unknown>>,
    }))
})

const actions = computed(() => {
  if (props.report.actions?.length) return props.report.actions
  if (props.report.next?.length) return props.report.next
  return ['再练一轮，把未达标能力补上。']
})

function evidenceText(value: unknown): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'object') {
    const item = value as Record<string, unknown>
    return String(item.question || item.quote || item.point || item.reason || item.evidence || '')
  }
  return String(value)
}
</script>

<template>
  <article class="review-sheet">
    <header class="sheet-head">
      <div class="sheet-title">
        <span class="sheet-kicker">答辩复盘单</span>
        <h1>{{ projectName }}</h1>
        <p>{{ reviewDate }} · 项目答辩训练</p>
      </div>
      <div class="verdict" :class="report.passed ? 'passed' : 'failed'">
        <strong>{{ report.passed ? '通过' : '未达标' }}</strong>
        <span>{{ levelLabel(report.level) }}</span>
      </div>
    </header>

    <section class="summary">
      <p>{{ report.summary || (report.passed ? '这次达到了能力目标，可以准备下一个项目。' : '这次还没有达到目标，按下面的缺口继续练。') }}</p>
      <p v-if="report.strengths?.length" class="strengths">
        还能讲清：{{ report.strengths.join('、') }}
      </p>
    </section>

    <section class="sheet-section">
      <header class="section-head">
        <span>01</span>
        <h2>最该补的 {{ weaknesses.length || 0 }} 个点</h2>
      </header>
      <div v-if="weaknesses.length" class="weak-grid">
        <article v-for="(item, index) in weaknesses" :key="`${item.tag}-${index}`" class="weak-card">
          <span class="weak-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <h3>{{ item.tag }}</h3>
          <p>{{ item.reason }}</p>
          <ul v-if="item.evidence.length" class="evidence-list">
            <li v-for="(evidence, evidenceIndex) in item.evidence" :key="evidenceIndex">
              {{ evidenceText(evidence) }}
            </li>
          </ul>
          <span class="weak-status">证据缺口</span>
        </article>
      </div>
      <p v-else class="empty-line">这次没有明显的薄弱点，保持状态。</p>
    </section>

    <section class="sheet-section">
      <header class="section-head">
        <span>02</span>
        <h2>能力证据</h2>
      </header>
      <ul v-if="report.capabilities.length" class="cap-list">
        <li v-for="item in report.capabilities" :key="item.tag_id" :class="{ met: item.met }">
          <span class="cap-mark">{{ item.met ? '✓' : '—' }}</span>
          <div>
            <strong>{{ item.tag }}</strong>
            <span>{{ item.target }} → {{ item.current || '未覆盖' }}</span>
            <small v-if="item.gap">{{ item.gap }}</small>
          </div>
        </li>
      </ul>
      <p v-else class="empty-line">还没有能力判定。</p>
    </section>

    <section class="sheet-section">
      <header class="section-head">
        <span>03</span>
        <h2>下一轮动作</h2>
      </header>
      <ol class="action-list">
        <li v-for="action in actions" :key="action">{{ action }}</li>
      </ol>
      <div class="sheet-actions">
        <button class="primary" type="button" @click="emit('repeat')">开始复练</button>
        <button class="ghost" type="button" @click="emit('print')">打印 / 导出 PDF</button>
      </div>
    </section>

    <footer class="sheet-foot">
      <span>知问 · 答辩作战室</span>
      <span>{{ report.passed ? '达到目标' : '继续练到能扛住追问' }}</span>
    </footer>
  </article>
</template>

<style scoped>
.review-sheet {
  --sheet: #f4efe4;
  --sheet-ink: #1b1b18;
  --sheet-muted: #6f6a5f;
  --sheet-line: #d7cdbd;
  --sheet-red: #a34838;
  --sheet-green: #2f6b4f;
  display: grid;
  gap: 24px;
  width: 100%;
  padding: 34px 38px 26px;
  border-radius: 4px;
  background: var(--sheet);
  color: var(--sheet-ink);
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.32);
}

.sheet-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 18px;
  border-bottom: 2px solid var(--sheet-ink);
}

.sheet-title {
  display: grid;
  gap: 4px;
}

.sheet-kicker {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  letter-spacing: 0.16em;
  color: var(--sheet-muted);
}

.sheet-title h1 {
  margin: 0;
  font-family: var(--font-serif, serif);
  font-size: clamp(28px, 3.4vw, 38px);
  line-height: 1.2;
  font-weight: 600;
}

.sheet-title p {
  margin: 0;
  color: var(--sheet-muted);
  font-size: 12px;
}

.verdict {
  flex: none;
  min-width: 78px;
  padding: 9px 12px;
  border: 2px solid currentColor;
  text-align: center;
  transform: rotate(-2deg);
}

.verdict strong,
.verdict span {
  display: block;
}

.verdict strong {
  font-family: var(--font-serif, serif);
  font-size: 18px;
  line-height: 1.2;
}

.verdict span {
  margin-top: 2px;
  font-family: var(--font-mono, monospace);
  font-size: 10px;
}

.verdict.failed {
  color: var(--sheet-red);
}

.verdict.passed {
  color: var(--sheet-green);
}

.summary {
  display: grid;
  gap: 6px;
}

.summary p {
  margin: 0;
  font-size: 15px;
  line-height: 1.75;
}

.strengths {
  color: var(--sheet-green);
  font-size: 12.5px !important;
}

.sheet-section {
  display: grid;
  gap: 12px;
}

.section-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--sheet-line);
}

.section-head span {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  color: var(--sheet-red);
}

.section-head h2 {
  margin: 0;
  font-family: var(--font-serif, serif);
  font-size: 19px;
  font-weight: 600;
}

.weak-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0 22px;
}

.weak-card {
  display: grid;
  align-content: start;
  gap: 6px;
  padding-top: 8px;
  border-top: 2px solid var(--sheet-ink);
}

.weak-index {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  color: var(--sheet-red);
}

.weak-card h3 {
  margin: 0;
  font-family: var(--font-serif, serif);
  font-size: 18px;
  font-weight: 600;
}

.weak-card p {
  margin: 0;
  color: var(--sheet-ink);
  font-size: 12.5px;
  line-height: 1.65;
}

.evidence-list {
  display: grid;
  gap: 4px;
  margin: 2px 0 0;
  padding-left: 15px;
  color: var(--sheet-muted);
  font-size: 13px;
  line-height: 1.55;
}

.weak-status {
  justify-self: start;
  margin-top: 2px;
  padding-bottom: 1px;
  border-bottom: 1px solid var(--sheet-red);
  color: var(--sheet-red);
  font-size: 10px;
  letter-spacing: 0.06em;
}

.cap-list {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.cap-list li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 8px;
  align-items: baseline;
  padding: 8px 0;
  border-bottom: 1px solid var(--sheet-line);
}

.cap-mark {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  color: var(--sheet-red);
}

.cap-list li.met .cap-mark {
  color: var(--sheet-green);
}

.cap-list div {
  display: grid;
  grid-template-columns: minmax(90px, auto) auto minmax(0, 1fr);
  gap: 4px 12px;
  align-items: baseline;
}

.cap-list strong {
  font-size: 13px;
}

.cap-list span {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--sheet-muted);
}

.cap-list small {
  color: var(--sheet-red);
  font-size: 11.5px;
}

.action-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 5px;
  font-size: 13.5px;
  line-height: 1.65;
}

.action-list li::marker {
  font-family: var(--font-mono, monospace);
  color: var(--sheet-red);
  font-size: 11px;
}

.sheet-actions {
  display: flex;
  gap: 10px;
  padding-top: 8px;
}

.primary,
.ghost {
  border-radius: 3px;
  font-size: 13px;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}

.primary {
  padding: 9px 16px;
  background: var(--sheet-ink);
  color: var(--sheet);
  font-weight: 600;
}

.primary:hover {
  background: #33332d;
}

.primary:active,
.ghost:active {
  transform: translateY(1px);
}

.ghost {
  padding: 8px 13px;
  border: 1px solid var(--sheet-line);
  color: var(--sheet-ink);
}

.ghost:hover {
  border-color: var(--sheet-muted);
}

.sheet-foot {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-top: 14px;
  border-top: 1px solid var(--sheet-line);
  color: var(--sheet-muted);
  font-family: var(--font-mono, monospace);
  font-size: 10px;
}

.empty-line {
  margin: 0;
  color: var(--sheet-muted);
  font-size: 13px;
  line-height: 1.65;
}

@media print {
  .review-sheet {
    box-shadow: none;
    padding: 0;
  }

  .sheet-actions {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .primary,
  .ghost {
    transition: none;
  }
}

@media (max-width: 760px) {
  .review-sheet {
    padding: 22px 20px 18px;
    gap: 20px;
  }

  .sheet-head {
    flex-direction: column;
    gap: 14px;
  }

  .verdict {
    transform: none;
  }

  .weak-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }

  .weak-card {
    border-top-width: 1px;
  }

  .cap-list div {
    grid-template-columns: minmax(0, 1fr);
    gap: 2px;
  }

  .sheet-actions {
    flex-direction: column;
  }

  .sheet-actions .primary,
  .sheet-actions .ghost {
    width: 100%;
  }
}
</style>
