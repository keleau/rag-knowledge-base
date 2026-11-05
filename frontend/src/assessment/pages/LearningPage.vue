<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { errorMessage } from '../../utils'
import { assessmentApi } from '../api'
import AbilityProgress from '../components/AbilityProgress.vue'
import QuestionEvidence from '../components/QuestionEvidence.vue'
import { buildAbilityStats } from '../learning'
import type { AssessmentDetail, Capability, PracticeItem } from '../types'
import { codeModeLabel, difficultyLabel } from '../ui'

const props = defineProps<{
  detail: AssessmentDetail
  codeContent: string | null
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'notify', kind: 'success' | 'error' | 'info', message: string): void
  (event: 'enter-exam'): void
}>()

const activeTag = ref<string>(props.detail.tags[0]?.id || '')
const currentIndex = ref(0)
const answers = ref<Record<string, string>>({})
const scoreDraft = ref<number | null>(null)
const saving = ref('')
const busy = ref(false)
const steps = ref<string[]>([])

const questions = computed(() => props.detail.practice.items.filter((item) => item.kind !== 'card'))
const cards = computed(() => props.detail.practice.items.filter((item) => item.kind === 'card'))
const tagQuestions = computed(() =>
  questions.value.filter((item) => !activeTag.value || item.tag_id === activeTag.value),
)
const currentQuestion = computed<PracticeItem | null>(() => tagQuestions.value[currentIndex.value] || null)
const currentCapability = computed<Capability | null>(
  () => props.detail.capabilities.find((item) => item.tag_id === activeTag.value) ?? null,
)
const currentCard = computed<PracticeItem | null>(
  () => cards.value.find((item) => item.tag_id === activeTag.value) ?? null,
)
const answered = computed(() => questions.value.filter((item) => item.user_answer).length)
const isLast = computed(() => currentIndex.value >= tagQuestions.value.length - 1)
const abilityStats = computed(() => buildAbilityStats(props.detail))

const answerDraft = computed({
  get: () =>
    currentQuestion.value
      ? answers.value[currentQuestion.value.id] ?? currentQuestion.value.user_answer ?? ''
      : '',
  set: (value: string) => {
    if (currentQuestion.value) answers.value[currentQuestion.value.id] = value
  },
})

const selfScores = [
  { label: '还不熟', value: 40 },
  { label: '基本掌握', value: 70 },
  { label: '能讲清', value: 95 },
]

watch(activeTag, () => {
  currentIndex.value = 0
  scoreDraft.value = currentQuestion.value?.self_score ?? null
})

watch(
  () => currentQuestion.value?.id,
  () => {
    scoreDraft.value = currentQuestion.value?.self_score ?? null
  },
)

watch(
  () => tagQuestions.value.length,
  (length) => {
    if (currentIndex.value >= length) currentIndex.value = Math.max(0, length - 1)
  },
)

function selectTag(id: string) {
  activeTag.value = id
}

function selectQuestion(index: number) {
  currentIndex.value = Math.max(0, Math.min(index, tagQuestions.value.length - 1))
}

async function save(item: PracticeItem, selfScore: number | null, advance = false) {
  if (saving.value) return
  const content = answerDraft.value.trim() || (item.user_answer ?? '').trim()
  if (!content && selfScore === null) {
    emit('notify', 'error', '先写下回答，或选一个自评')
    return
  }
  saving.value = item.id
  try {
    await assessmentApi.answerPractice(item.id, content, selfScore)
    answers.value[item.id] = content
    emit('changed')
    emit('notify', 'success', advance ? '已保存，进入下一题' : '回答已保存')
    if (advance) {
      if (!isLast.value) currentIndex.value += 1
      else emit('notify', 'info', '这个能力练完了，可以换一个能力，或生成模拟考')
    }
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    saving.value = ''
  }
}

async function morePractice() {
  if (busy.value) return
  busy.value = true
  const controller = new AbortController()
  try {
    await assessmentApi.morePractice(
      props.detail.session.id,
      (event, data) => {
        if (event === 'step') steps.value.push(String((data as unknown as { summary?: string }).summary || ''))
      },
      controller.signal,
    )
    emit('changed')
    emit('notify', 'success', '已补充练习题')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function startExam() {
  if (busy.value) return
  busy.value = true
  steps.value = []
  const controller = new AbortController()
  let generated = false
  try {
    await assessmentApi.startExam(
      props.detail.session.id,
      props.detail.session.version,
      (event, data) => {
        if (event === 'step') {
          const payload = data as unknown as {
            label?: string
            summary?: string
            rejected?: Array<{ prompt: string; reason: string }>
          }
          const rejected = (payload.rejected || []).map((item) => `丢弃「${item.prompt}」：${item.reason}`)
          steps.value.push([payload.label, payload.summary, ...rejected].filter(Boolean).join(' · '))
        }
        if (event === 'done') generated = true
      },
      controller.signal,
    )
    emit('changed')
    emit('enter-exam')
  } catch (error) {
    if (generated) {
      emit('changed')
      emit('notify', 'info', '试卷已生成，请刷新后进入考试')
    } else {
      emit('notify', 'error', errorMessage(error))
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="learning-page">
    <AbilityProgress
      :stats="abilityStats"
      :active-tag="activeTag"
      :answered="answered"
      :total="questions.length"
      :busy="busy"
      :steps="steps"
      @select="selectTag"
      @more="morePractice"
      @exam="startExam"
    />

    <section class="question-stage">
      <header class="stage-top">
        <div>
          <span class="stage-kicker">演练 / {{ props.detail.practice.cycle > 0 ? `第 ${props.detail.practice.cycle} 轮复练` : '第一轮' }}</span>
          <strong>{{ currentCapability?.tag || '选择一个能力' }}</strong>
        </div>
        <span class="stage-position">
          {{ tagQuestions.length ? currentIndex + 1 : 0 }} / {{ tagQuestions.length }}
        </span>
      </header>

      <template v-if="currentQuestion">
        <div class="question-meta">
          <span class="question-tag">{{ currentQuestion.tag }}</span>
          <span>{{ difficultyLabel(currentQuestion.difficulty) }}</span>
          <span v-if="currentQuestion.kind === 'code_question'">{{ codeModeLabel(currentQuestion.code_mode) }}</span>
          <span v-if="currentQuestion.user_answer" class="saved">已保存</span>
        </div>

        <h1 class="question-prompt">{{ currentQuestion.prompt }}</h1>
        <p v-if="currentQuestion.kind === 'code_question'" class="code-hint">
          回答时提到：{{ currentQuestion.symbols.join('、') || '相关符号' }}
        </p>

        <textarea
          v-model="answerDraft"
          class="answer-box"
          rows="7"
          placeholder="像面试时那样口述：先给结论，再说项目里的具体做法和取舍"
        ></textarea>

        <div class="score-row">
          <span class="score-label">自评</span>
          <button
            v-for="score in selfScores"
            :key="score.value"
            type="button"
            class="score-chip"
            :class="{ picked: scoreDraft === score.value }"
            @click="scoreDraft = score.value"
          >
            {{ score.label }}
          </button>
        </div>

        <div class="stage-actions">
          <button class="ghost" type="button" :disabled="currentIndex === 0" @click="selectQuestion(currentIndex - 1)">
            上一题
          </button>
          <button class="ghost" type="button" :disabled="saving === currentQuestion.id" @click="save(currentQuestion, scoreDraft)">
            只保存
          </button>
          <button
            class="primary"
            type="button"
            :disabled="saving === currentQuestion.id"
            @click="save(currentQuestion, scoreDraft, true)"
          >
            {{ saving === currentQuestion.id ? '保存中…' : isLast ? '保存并完成' : '保存并下一题' }}
          </button>
        </div>
      </template>

      <div v-else class="stage-empty">
        <strong>这个能力还没有练习题。</strong>
        <p>换一个能力，或在左侧「再来几道」生成新的练习。</p>
      </div>
    </section>

    <QuestionEvidence
      :question="currentQuestion"
      :capability="currentCapability"
      :card="currentCard"
      :code-content="props.codeContent"
    />
  </div>
</template>

<style scoped>
.learning-page {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 280px;
  gap: 20px;
  align-items: start;
}

.question-stage {
  min-width: 0;
  padding: 2px 2px 0;
}

.stage-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line, #2c3a32);
}

.stage-top div {
  display: grid;
  gap: 3px;
}

.stage-kicker {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--amber, #d7a64f);
}

.stage-top strong {
  font-family: var(--font-serif, serif);
  font-size: 19px;
  font-weight: 600;
}

.stage-position {
  flex: none;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--muted, #a6b0a7);
}

.question-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 20px 0 14px;
  font-size: 12px;
  color: var(--muted, #a6b0a7);
}

.question-tag {
  color: var(--amber, #d7a64f);
}

.saved {
  color: #8fc9a9;
}

.question-prompt {
  margin: 0 0 10px;
  font-family: var(--font-serif, serif);
  font-size: clamp(22px, 2.4vw, 28px);
  line-height: 1.4;
  font-weight: 600;
  text-wrap: pretty;
}

.code-hint {
  margin: 0 0 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #8fc9a9;
}

.answer-box {
  width: 100%;
  min-height: 180px;
  margin-top: 4px;
  padding: 12px 14px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 10px;
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

.score-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.score-label {
  font-size: 12px;
  color: var(--muted, #a6b0a7);
}

.score-chip {
  padding: 5px 11px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 999px;
  color: var(--ink-soft, #d7d0c2);
  font-size: 12px;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.score-chip:hover {
  border-color: var(--line-strong, #405146);
}

.score-chip.picked {
  border-color: var(--amber, #d7a64f);
  background: rgba(215, 166, 79, 0.1);
  color: var(--amber, #d7a64f);
}

.stage-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line, #2c3a32);
}

.stage-empty {
  display: grid;
  gap: 6px;
  padding: 48px 0;
  color: var(--muted, #a6b0a7);
}

.stage-empty strong {
  color: var(--ink-soft, #d7d0c2);
  font-size: 15px;
}

.stage-empty p {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
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
  .score-chip,
  .primary,
  .ghost {
    transition: none;
  }
}

@media (max-width: 1120px) {
  .learning-page {
    grid-template-columns: 200px minmax(0, 1fr) 250px;
    gap: 16px;
  }
}

@media (max-width: 980px) {
  .learning-page {
    grid-template-columns: 190px minmax(0, 1fr);
  }
}

@media (max-width: 700px) {
  .learning-page {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }

  .stage-actions {
    flex-wrap: wrap;
    justify-content: stretch;
  }

  .stage-actions .primary {
    flex-basis: 100%;
    order: 3;
  }
}
</style>
