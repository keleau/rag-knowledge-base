<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { errorMessage } from '../../utils'
import { assessmentApi } from '../api'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'notify', kind: 'success' | 'error' | 'info', message: string): void
  (event: 'next'): void
}>()

const grading = ref(false)
const steps = ref<string[]>([])
const done = ref(props.detail.exam.answers.length > 0)

const questions = computed(() => props.detail.exam.questions)
const answerMap = computed(() => new Map(props.detail.exam.answers.map((item) => [item.question_id, item])))
const total = computed(() => props.detail.exam.answers.reduce((sum, item) => sum + (item.score || 0), 0))
const maxTotal = computed(() => questions.value.length * 10 || 1)

async function grade() {
  if (grading.value) return
  grading.value = true
  const controller = new AbortController()
  try {
    await assessmentApi.gradeExam(
      props.detail.session.id,
      (event, data) => {
        if (event === 'step') steps.value.push(String((data as { label?: string }).label || ''))
      },
      controller.signal,
    )
    done.value = true
    emit('changed')
    emit('notify', 'success', '阅卷完成')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    grading.value = false
  }
}

onMounted(() => {
  const needsGrading = props.detail.exam.answers.some((item) => item.score === null)
  if (needsGrading) grade()
})
</script>

<template>
  <div class="grading-page">
    <section class="score-top">
      <div class="score">{{ Math.round(total) }}<span>/{{ maxTotal }}</span></div>
      <div class="score-meta">
        <p>客观题由规则精确判分；主观题按 rubric 命中，命中必须引用你的原句。</p>
        <p v-if="props.detail.weak_points.length" class="weak">
          薄弱点：{{ props.detail.weak_points.map((item) => item.tag).join('、') }}
        </p>
        <p v-if="grading">阅卷中…</p>
      </div>
      <button v-if="done" class="primary" type="button" @click="emit('next')">开始面试</button>
    </section>

    <article v-for="(question, index) in questions" :key="question.id" class="grade-card">
      <header>
        <span class="index">{{ index + 1 }}</span>
        <span class="tag">{{ question.tag }}</span>
        <span class="score-line">
          {{ answerMap.get(question.id)?.score ?? '—' }} / {{ answerMap.get(question.id)?.max_score ?? 10 }}
        </span>
        <span v-if="answerMap.get(question.id)?.needs_review" class="review">待复核</span>
      </header>
      <p class="prompt">{{ question.prompt }}</p>
      <p class="your-answer"><strong>你的回答：</strong>{{ answerMap.get(question.id)?.content || '（未作答）' }}</p>
      <ul class="hits">
        <li v-for="(hit, hitIndex) in answerMap.get(question.id)?.hits || []" :key="hitIndex" :class="{ miss: !hit.hit }">
          {{ hit.hit ? '✓' : '✗' }} {{ hit.point }}
          <em v-if="hit.evidence">「{{ hit.evidence }}」</em>
        </li>
      </ul>
      <p v-if="answerMap.get(question.id)?.review_note" class="review-note">
        复核说明：{{ answerMap.get(question.id)?.review_note }}
      </p>
    </article>

    <section v-if="props.detail.weak_points.length" class="weak-list">
      <h3>薄弱点</h3>
      <div v-for="item in props.detail.weak_points" :key="item.id" class="weak-item">
        <strong>{{ item.tag }}</strong>
        <p>{{ item.reason }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.grading-page {
  display: grid;
  gap: 14px;
}
.score-top {
  display: flex;
  align-items: center;
  gap: 18px;
  border: 1px solid var(--line, #2c2f36);
  border-radius: 14px;
  padding: 16px 20px;
  background: var(--panel, #17191f);
  flex-wrap: wrap;
}
.score {
  font-size: 34px;
  font-weight: 700;
  color: var(--accent, #e8b04b);
}
.score span {
  font-size: 14px;
  color: var(--muted, #8a8f9a);
}
.score-meta {
  flex: 1;
  font-size: 12.5px;
  color: var(--muted, #8a8f9a);
}
.score-meta p {
  margin: 2px 0;
}
.weak {
  color: #d58e5a;
}
.grade-card {
  border: 1px solid var(--line, #2c2f36);
  border-radius: 14px;
  padding: 14px 18px;
  background: var(--panel, #17191f);
}
.grade-card header {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 12px;
  color: var(--muted, #8a8f9a);
  margin-bottom: 8px;
}
.index {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(232, 176, 75, 0.16);
  color: #e8b04b;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}
.score-line {
  margin-left: auto;
  color: #b8c0cc;
}
.review {
  color: #e38a8a;
  border: 1px solid rgba(227, 138, 138, 0.45);
  border-radius: 999px;
  padding: 1px 8px;
}
.prompt {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.6;
}
.your-answer {
  font-size: 13px;
  color: #b8c0cc;
  background: #0f1014;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 0 0 8px;
  white-space: pre-wrap;
}
.hits {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
  font-size: 13px;
  color: #5ec98a;
}
.hits li.miss {
  color: #d58e5a;
}
.hits em {
  font-style: normal;
  color: var(--muted, #8a8f9a);
}
.review-note {
  font-size: 12px;
  color: #e38a8a;
}
.weak-list h3 {
  font-size: 15px;
  margin: 8px 0;
}
.weak-item {
  border-left: 2px solid #d58e5a;
  padding-left: 10px;
  margin-bottom: 10px;
  font-size: 13px;
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
</style>
