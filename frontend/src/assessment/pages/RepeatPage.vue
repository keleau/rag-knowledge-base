<script setup lang="ts">
import { computed, ref } from 'vue'
import { errorMessage } from '../../utils'
import { assessmentApi } from '../api'
import QuestionCard from '../components/QuestionCard.vue'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'notify', kind: 'success' | 'error' | 'info', message: string): void
  (event: 'report'): void
}>()

const answers = ref<Record<string, string>>({})
const busy = ref(false)
const generated = ref(false)

const items = computed(() => props.detail.practice.items.filter((item) => item.kind !== 'card'))
const answered = computed(() => items.value.filter((item) => (answers.value[item.id] || '').trim()).length)

function asQuestion(item: AssessmentDetail['practice']['items'][number]) {
  return {
    id: item.id,
    tag_id: item.tag_id,
    tag: item.tag,
    type: (item.kind === 'code_question' ? 'code' : 'short_answer') as 'code' | 'short_answer',
    code_mode: item.code_mode,
    prompt: item.prompt,
    options: [],
    difficulty: item.difficulty,
    source_quote: item.source_quote,
    source_file: item.source_file,
    line_start: item.line_start,
    line_end: item.line_end,
    symbols: item.symbols,
  }
}

async function submit() {
  if (busy.value || answered.value === 0) return
  busy.value = true
  try {
    const result = await assessmentApi.submitRepeat(
      props.detail.session.id,
      props.detail.session.version,
      items.value
        .filter((item) => (answers.value[item.id] || '').trim())
        .map((item) => ({ question_id: item.id, content: answers.value[item.id] })),
    )
    emit('changed')
    emit('notify', result.evaluation?.passed ? 'success' : 'info', result.evaluation?.passed ? '复练完成，已达标' : '复练完成，仍有差距')
    emit('report')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

function markGenerated() {
  generated.value = true
}
</script>

<template>
  <div class="repeat-page">
    <section class="repeat-top">
      <div>
        <strong>复练 {{ props.detail.practice.cycle }}</strong>
        <span class="muted">只针对未达标能力出题，完成 {{ items.length }} 道后重新判定。</span>
      </div>
      <span class="progress">{{ answered }}/{{ items.length }}</span>
    </section>

    <div v-if="items.length" class="list">
      <QuestionCard v-for="(item, index) in items" :key="item.id" :question="asQuestion(item)" :index="index">
        <textarea v-model="answers[item.id]" class="answer-box" rows="4" placeholder="写下你的回答"></textarea>
      </QuestionCard>
    </div>
    <p v-else class="empty">复练题还在生成中。</p>

    <div class="actions">
      <button class="primary" type="button" :disabled="busy || answered === 0" @click="submit">
        {{ busy ? '重新判定中…' : '提交并重新判定' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.repeat-page {
  display: grid;
  gap: 16px;
}
.repeat-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid var(--line, #2c2f36);
  border-radius: 14px;
  padding: 12px 16px;
  background: var(--panel, #17191f);
  font-size: 13px;
  flex-wrap: wrap;
  gap: 8px;
}
.muted {
  color: var(--muted, #8a8f9a);
  font-size: 12px;
  margin-left: 6px;
}
.progress {
  color: var(--accent, #e8b04b);
  font-weight: 600;
}
.list {
  display: grid;
  gap: 14px;
}
.empty {
  color: var(--muted, #8a8f9a);
}
.answer-box {
  width: 100%;
  margin-top: 10px;
  background: #0f1014;
  border: 1px solid var(--line, #2c2f36);
  border-radius: 10px;
  padding: 10px 12px;
  color: inherit;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
.primary {
  border: 0;
  border-radius: 10px;
  padding: 9px 18px;
  background: var(--accent, #e8b04b);
  color: #15161a;
  font-weight: 600;
  cursor: pointer;
}
.primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
