<script setup lang="ts">
import type { ExamQuestion } from '../types'
import { codeModeLabel, difficultyLabel } from '../ui'

defineProps<{
  question: ExamQuestion
  index?: number
}>()
</script>

<template>
  <article class="question-card">
    <header class="q-head">
      <span class="q-index" v-if="index !== undefined">{{ index + 1 }}</span>
      <span class="q-tag">{{ question.tag }}</span>
      <span v-if="question.type === 'code'" class="q-mode">{{ codeModeLabel(question.code_mode) }}</span>
      <span class="q-difficulty">{{ difficultyLabel(question.difficulty) }}</span>
    </header>
    <p class="q-prompt">{{ question.prompt }}</p>
    <div v-if="question.type === 'code' && question.source_file" class="q-source">
      <code>{{ question.source_file }}<template v-if="question.line_start"> · 第 {{ question.line_start }}–{{ question.line_end }} 行</template></code>
      <span v-if="question.symbols.length" class="q-symbols">需要提到：{{ question.symbols.join('、') }}</span>
    </div>
    <div v-else-if="question.source_quote" class="q-source">
      <span>依据：「{{ question.source_quote }}」</span>
    </div>
    <slot />
  </article>
</template>

<style scoped>
.question-card {
  border: 1px solid var(--line, #2c2f36);
  border-radius: 14px;
  padding: 16px 18px;
  background: var(--panel, #17191f);
}
.q-head {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--muted, #8a8f9a);
  margin-bottom: 8px;
}
.q-index {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--accent, #e8b04b);
  color: #15161a;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}
.q-mode {
  color: #7fb8ff;
}
.q-prompt {
  margin: 0 0 10px;
  font-size: 15px;
  line-height: 1.65;
}
.q-source {
  font-size: 12px;
  color: var(--muted, #8a8f9a);
  border-left: 2px solid var(--accent, #e8b04b);
  padding-left: 10px;
  display: grid;
  gap: 4px;
}
.q-symbols {
  color: #5ec98a;
}
</style>
