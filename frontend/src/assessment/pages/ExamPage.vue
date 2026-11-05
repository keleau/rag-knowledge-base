<script setup lang="ts">
import { computed, ref } from 'vue'
import { errorMessage } from '../../utils'
import { assessmentApi } from '../api'
import CodeViewer from '../components/CodeViewer.vue'
import type { AssessmentDetail } from '../types'
import { codeModeLabel, difficultyLabel, newIdempotencyKey } from '../ui'

const props = defineProps<{
  detail: AssessmentDetail
  codeContent: string | null
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'notify', kind: 'success' | 'error' | 'info', message: string): void
  (event: 'submitted'): void
}>()

const answers = ref<Record<string, string>>(
  Object.fromEntries(props.detail.exam.answers.map((item) => [item.question_id, item.content])),
)
const submitting = ref(false)
const active = ref(0)
const idempotencyKey = ref(newIdempotencyKey('submit'))

const questions = computed(() => props.detail.exam.questions)
const current = computed(() => questions.value[active.value] || null)
const answeredCount = computed(
  () => questions.value.filter((item) => (answers.value[item.id] || '').trim()).length,
)
const progress = computed(() =>
  questions.value.length ? Math.round((answeredCount.value / questions.value.length) * 100) : 0,
)

const answerDraft = computed({
  get: () => (current.value ? answers.value[current.value.id] ?? '' : ''),
  set: (value: string) => {
    if (current.value) answers.value[current.value.id] = value
  },
})

function optionValue(option: string): string {
  return (/^\s*([A-Da-d])[\s.、:：]/.exec(option)?.[1] || option.trim().slice(0, 1)).toUpperCase()
}

function move(delta: number) {
  active.value = Math.max(0, Math.min(active.value + delta, questions.value.length - 1))
}

async function submit() {
  if (submitting.value) return
  if (answeredCount.value < questions.value.length) {
    emit('notify', 'error', `还有 ${questions.value.length - answeredCount.value} 道题没有作答`)
    return
  }
  submitting.value = true
  try {
    await assessmentApi.submitExam(
      props.detail.session.id,
      props.detail.session.version,
      questions.value.map((item) => ({ question_id: item.id, content: answers.value[item.id] || '' })),
      idempotencyKey.value,
      false,
    )
    emit('changed')
    emit('submitted')
  } catch (error) {
    const message = errorMessage(error)
    if (message.includes('409') || message.includes('已被修改') || message.includes('不能从')) {
      emit('changed')
      emit('submitted')
      return
    }
    emit('notify', 'error', message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="exam-page">
    <header class="exam-head">
      <div class="exam-title">
        <span class="exam-kicker">模拟考</span>
        <strong>第 {{ questions.length ? active + 1 : 0 }} / {{ questions.length }} 题</strong>
      </div>
      <div class="exam-progress">
        <span>{{ answeredCount }} 题已答</span>
        <i :style="{ width: `${progress}%` }"></i>
      </div>
    </header>

    <section v-if="current" class="question-sheet">
      <div class="question-meta">
        <span class="question-tag">{{ current.tag }}</span>
        <span>{{ difficultyLabel(current.difficulty) }}</span>
        <span v-if="current.type === 'code'">{{ codeModeLabel(current.code_mode) }}</span>
      </div>

      <h1 class="question-prompt">{{ current.prompt }}</h1>

      <CodeViewer
        v-if="current.type === 'code' && props.codeContent"
        :content="props.codeContent"
        :start="current.line_start"
        :end="current.line_end"
        :file="current.source_file"
      />

      <div v-if="current.type === 'single_choice'" class="options">
        <label v-for="option in current.options" :key="option" class="option" :class="{ picked: answerDraft === optionValue(option) }">
          <input
            type="radio"
            :name="current.id"
            :value="optionValue(option)"
            v-model="answerDraft"
          />
          <span>{{ option }}</span>
        </label>
      </div>
      <textarea
        v-else
        v-model="answerDraft"
        class="answer-box"
        rows="9"
        placeholder="闭卷作答：先给结论，再写项目里的具体做法和取舍"
      ></textarea>

      <p v-if="current.type === 'code'" class="code-hint">
        需要提到：{{ current.symbols.join('、') || '相关符号' }}
      </p>
    </section>

    <div v-else class="exam-empty">
      <strong>这份试卷还没有题目。</strong>
      <p>回到演练页生成模拟考后再进入。</p>
    </div>

    <footer class="exam-foot">
      <div class="foot-nav">
        <button class="ghost" type="button" :disabled="active === 0" @click="move(-1)">上一题</button>
        <button class="ghost" type="button" :disabled="active >= questions.length - 1" @click="move(1)">下一题</button>
      </div>
      <span class="foot-count">{{ answeredCount }}/{{ questions.length }} 已答</span>
      <button class="primary" type="button" :disabled="submitting || !questions.length" @click="submit">
        {{ submitting ? '提交中…' : '提交试卷' }}
      </button>
    </footer>
  </div>
</template>

<style scoped>
.exam-page {
  display: grid;
  gap: 16px;
  width: min(820px, 100%);
  margin: 0 auto;
}

.exam-head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line, #2c3a32);
}

.exam-title {
  display: grid;
  gap: 3px;
}

.exam-kicker {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--amber, #d7a64f);
}

.exam-title strong {
  font-family: var(--font-serif, serif);
  font-size: 21px;
  font-weight: 600;
}

.exam-progress {
  display: grid;
  gap: 6px;
  width: 190px;
  text-align: right;
  color: var(--muted, #a6b0a7);
  font-size: 11px;
}

.exam-progress i {
  display: block;
  height: 4px;
  border-radius: 999px;
  background: var(--amber, #d7a64f);
  transition: width 0.25s ease;
}

.exam-progress::before {
  content: '';
  grid-row: 2;
  height: 4px;
  border-radius: 999px;
  background: rgba(245, 242, 234, 0.1);
}

.exam-progress i {
  grid-row: 2;
  grid-column: 1;
  justify-self: start;
  max-width: 100%;
}

.question-sheet {
  display: grid;
  gap: 10px;
  padding: 20px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 12px;
  background: var(--panel, #171d19);
}

.question-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted, #a6b0a7);
}

.question-tag {
  color: var(--amber, #d7a64f);
}

.question-prompt {
  margin: 0 0 6px;
  font-family: var(--font-serif, serif);
  font-size: clamp(21px, 2.2vw, 26px);
  line-height: 1.45;
  font-weight: 600;
  text-wrap: pretty;
}

.options {
  display: grid;
  gap: 8px;
}

.option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 9px;
  color: var(--ink-soft, #d7d0c2);
  cursor: pointer;
  font-size: 13.5px;
  line-height: 1.55;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.option:hover {
  border-color: var(--line-strong, #405146);
}

.option.picked {
  border-color: var(--amber, #d7a64f);
  background: rgba(215, 166, 79, 0.08);
}

.option input {
  margin-top: 3px;
  accent-color: var(--amber, #d7a64f);
}

.answer-box {
  width: 100%;
  min-height: 210px;
  padding: 12px 14px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 9px;
  background: #0b100e;
  color: var(--ink, #f2eee3);
  font-size: 14px;
  line-height: 1.75;
  resize: vertical;
}

.answer-box:focus {
  outline: 2px solid var(--amber, #d7a64f);
  outline-offset: 1px;
}

.code-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #8fc9a9;
}

.exam-foot {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0 4px;
  border-top: 1px solid var(--line, #2c3a32);
  background: var(--paper-deep, #0d1210);
}

.foot-nav {
  display: flex;
  gap: 8px;
}

.foot-count {
  margin-left: auto;
  color: var(--muted, #a6b0a7);
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
}

.exam-empty {
  display: grid;
  gap: 6px;
  padding: 48px 0;
  color: var(--muted, #a6b0a7);
}

.exam-empty strong {
  color: var(--ink-soft, #d7d0c2);
  font-size: 15px;
}

.exam-empty p {
  margin: 0;
  font-size: 13px;
}

.primary,
.ghost {
  border-radius: 9px;
  font-size: 13px;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}

.primary {
  padding: 9px 16px;
  background: var(--amber, #d7a64f);
  color: #1b1b18;
  font-weight: 650;
}

.primary:hover {
  background: #c99b4f;
}

.primary:active,
.ghost:active {
  transform: translateY(1px) scale(0.99);
}

.primary:disabled,
.ghost:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.ghost {
  padding: 8px 13px;
  border: 1px solid var(--line, #2c3a32);
  color: var(--ink-soft, #d7d0c2);
}

.ghost:hover {
  border-color: var(--line-strong, #405146);
}

@media (prefers-reduced-motion: reduce) {
  .option,
  .exam-progress i,
  .primary,
  .ghost {
    transition: none;
  }
}

@media (max-width: 700px) {
  .exam-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .exam-progress {
    width: 100%;
    text-align: left;
  }

  .question-sheet {
    padding: 16px;
  }

  .exam-foot {
    flex-wrap: wrap;
  }

  .foot-count {
    order: 3;
    width: 100%;
    margin-left: 0;
  }

  .exam-foot .primary {
    flex: 1;
  }
}
</style>
