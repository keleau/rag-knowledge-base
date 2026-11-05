<script setup lang="ts">
import CodeViewer from './CodeViewer.vue'
import type { Capability, PracticeItem } from '../types'
import { levelLabel } from '../ui'

defineProps<{
  question: PracticeItem | null
  capability: Capability | null
  card: PracticeItem | null
  codeContent: string | null
}>()
</script>

<template>
  <aside class="evidence-rail" aria-label="题目证据">
    <header class="evidence-head">
      <span>证据</span>
      <em>SOURCE</em>
    </header>

    <section v-if="question" class="evidence-block">
      <h3>这道题从哪来</h3>
      <CodeViewer
        v-if="question.kind === 'code_question' && codeContent"
        :content="codeContent"
        :start="question.line_start"
        :end="question.line_end"
        :file="question.source_file"
        :file-line="question.source_quote ? [question.source_quote.trim()] : null"
      />
      <blockquote v-else-if="question.source_quote">
        {{ question.source_quote }}
      </blockquote>
      <p v-else class="muted">这道题没有可展示的来源。</p>
    </section>

    <section v-if="capability" class="evidence-block">
      <h3>能力目标</h3>
      <p class="cap-line">
        <strong>{{ capability.tag }}</strong>
        <span>目标 {{ levelLabel(capability.target_level) }}</span>
      </p>
      <ul v-if="capability.acceptance.length" class="cap-list">
        <li v-for="item in capability.acceptance" :key="item">{{ item }}</li>
      </ul>
      <span class="cap-status" :class="{ met: capability.current_level }">
        {{ capability.current_level ? `当前 ${levelLabel(capability.current_level)}` : '当前未覆盖' }}
      </span>
    </section>

    <section v-if="card" class="evidence-block">
      <h3>知识卡</h3>
      <p class="card-title">{{ card.prompt }}</p>
      <p>{{ card.answer }}</p>
      <p v-if="card.source_quote" class="muted">依据：「{{ card.source_quote }}」</p>
    </section>

    <section v-if="question?.explanation" class="evidence-block">
      <h3>考察点</h3>
      <p>{{ question.explanation }}</p>
    </section>

    <section v-if="!question" class="evidence-block">
      <h3>还没有选中题目</h3>
      <p class="muted">从左侧选择一个能力，题目和它的证据会一起出现。</p>
    </section>
  </aside>
</template>

<style scoped>
.evidence-rail {
  min-width: 0;
  padding-left: 18px;
  border-left: 1px solid var(--line, #2c3a32);
}

.evidence-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, #2c3a32);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--muted, #a6b0a7);
}

.evidence-head em {
  font-family: var(--font-mono, monospace);
  font-style: normal;
  font-size: 9.5px;
  color: var(--amber, #d7a64f);
}

.evidence-block {
  display: grid;
  gap: 8px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line, #2c3a32);
}

.evidence-block:last-child {
  border-bottom: 0;
}

.evidence-block h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft, #d7d0c2);
}

.evidence-block p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.65;
}

.evidence-block blockquote {
  margin: 0;
  padding: 0 0 0 12px;
  border-left: 2px solid var(--amber, #d7a64f);
  color: var(--ink-soft, #d7d0c2);
  font-size: 12.5px;
  line-height: 1.7;
}

.cap-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.cap-line strong {
  font-size: 13px;
}

.cap-line span {
  color: var(--muted, #a6b0a7);
  font-size: 11px;
}

.cap-list {
  display: grid;
  gap: 4px;
  margin: 0;
  padding-left: 16px;
  color: var(--muted, #a6b0a7);
  font-size: 12px;
  line-height: 1.6;
}

.cap-status {
  justify-self: start;
  padding-bottom: 1px;
  border-bottom: 1px solid currentColor;
  font-size: 11px;
  color: var(--danger, #d97b63);
}

.cap-status.met {
  color: #8fc9a9;
}

.card-title {
  font-weight: 600;
  color: var(--ink-soft, #d7d0c2);
}

.muted {
  color: var(--muted, #a6b0a7);
}

@media (max-width: 980px) {
  .evidence-rail {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0 20px;
    padding: 16px 0 0;
    border-top: 1px solid var(--line, #2c3a32);
    border-left: 0;
  }

  .evidence-block:nth-child(odd) {
    padding-right: 20px;
    border-right: 1px solid var(--line, #2c3a32);
  }
}

@media (max-width: 700px) {
  .evidence-rail {
    display: block;
    padding: 14px 0 0;
  }

  .evidence-block:nth-child(odd) {
    padding-right: 0;
    border-right: 0;
  }
}
</style>
