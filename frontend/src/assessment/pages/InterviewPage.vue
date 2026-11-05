<script setup lang="ts">
import { computed, ref } from 'vue'
import { errorMessage } from '../../utils'
import { assessmentApi } from '../api'
import InterviewRecord from '../components/InterviewRecord.vue'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'notify', kind: 'success' | 'error' | 'info', message: string): void
  (event: 'report'): void
}>()

const answer = ref('')
const busy = ref(false)

const turns = computed(() => props.detail.interview.turns)
const current = computed(() => turns.value[turns.value.length - 1] || null)
const hasTurns = computed(() => turns.value.length > 0)
const canAnswer = computed(() => current.value?.status === 'asking')
const canReport = computed(
  () => hasTurns.value && !canAnswer.value && (props.detail.interview.current_round >= 3 || !current.value?.question),
)
const focusTag = computed(
  () => current.value?.tag || turns.value[turns.value.length - 1]?.tag || props.detail.weak_points[0]?.tag || '薄弱点',
)
const weakTags = computed(() => props.detail.weak_points.map((item) => item.tag))

async function start() {
  if (busy.value) return
  busy.value = true
  try {
    await assessmentApi.startInterview(props.detail.session.id, props.detail.session.version)
    emit('changed')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function send() {
  const content = answer.value.trim()
  if (!content || busy.value) return
  busy.value = true
  try {
    const result = await assessmentApi.answerInterview(props.detail.session.id, content, null)
    answer.value = ''
    emit('changed')
    if (result.finished) {
      emit('notify', 'info', '面试轮次已结束，可以生成报告')
    }
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function toReport() {
  if (busy.value) return
  busy.value = true
  try {
    await assessmentApi.makeReport(props.detail.session.id, null, () => undefined, new AbortController().signal)
    emit('changed')
    emit('report')
  } catch (error) {
    await new Promise((resolve) => window.setTimeout(resolve, 200))
    try {
      await assessmentApi.getReport(props.detail.session.id)
      emit('changed')
      emit('report')
    } catch {
      emit('notify', 'error', errorMessage(error))
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="interview-page">
    <header class="record-head">
      <div>
        <span class="record-kicker">实战 / 追问记录</span>
        <strong>第 {{ props.detail.interview.current_round || 0 }} / 3 轮</strong>
        <span class="record-focus">聚焦：{{ focusTag }}</span>
      </div>
      <span v-if="canReport" class="record-note">记录完整，可以生成复盘</span>
    </header>

    <section v-if="!hasTurns" class="briefing">
      <span class="briefing-index">01</span>
      <h1>现在开始模拟面试。</h1>
      <p>
        面试官只追你的薄弱点。答不清会继续追问，答得空泛会要求你拿项目里的证据。
      </p>
      <div class="weak-tags">
        <span v-for="tag in weakTags" :key="tag">{{ tag }}</span>
        <span v-if="!weakTags.length">按能力目标开始</span>
      </div>
      <button class="primary" type="button" :disabled="busy" @click="start">
        {{ busy ? '准备面试…' : '开始模拟面试' }}
      </button>
    </section>

    <InterviewRecord v-else :turns="turns" />

    <section v-if="canAnswer" class="record-composer">
      <div class="record-composer-head">
        <span>记录回答</span>
        <em>{{ current?.tag }}</em>
      </div>
      <textarea
        v-model="answer"
        class="answer-box"
        rows="5"
        placeholder="像面试一样口述：先给结论，再拿项目里的具体做法和取舍作证"
        @keydown.ctrl.enter="send"
      ></textarea>
      <div class="record-composer-foot">
        <span>Ctrl + Enter 提交</span>
        <button class="primary" type="button" :disabled="busy || !answer.trim()" @click="send">
          {{ busy ? '评分中…' : '记录回答' }}
        </button>
      </div>
    </section>

    <section v-else-if="canReport" class="finish">
      <p>追问已经记录完整。生成复盘，看看这轮还差什么。</p>
      <button class="primary" type="button" :disabled="busy" @click="toReport">
        {{ busy ? '生成中…' : '生成报告并判定' }}
      </button>
    </section>
  </div>
</template>

<style scoped>
.interview-page {
  display: grid;
  gap: 18px;
  width: min(840px, 100%);
  margin: 0 auto;
}

.record-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line, #2c3a32);
}

.record-head > div {
  display: grid;
  gap: 3px;
}

.record-kicker {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--amber, #d7a64f);
}

.record-head strong {
  font-family: var(--font-serif, serif);
  font-size: 21px;
  font-weight: 600;
}

.record-focus {
  font-size: 12px;
  color: var(--muted, #a6b0a7);
}

.record-note {
  font-size: 11px;
  color: #8fc9a9;
}

.briefing {
  display: grid;
  justify-items: start;
  gap: 12px;
  padding: 26px 0;
  border-bottom: 1px solid var(--line, #2c3a32);
}

.briefing-index {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--amber, #d7a64f);
}

.briefing h1 {
  margin: 0;
  font-family: var(--font-serif, serif);
  font-size: clamp(26px, 3vw, 34px);
  line-height: 1.3;
  font-weight: 600;
}

.briefing p {
  margin: 0;
  max-width: 56ch;
  color: var(--muted, #a6b0a7);
  font-size: 13.5px;
  line-height: 1.7;
}

.weak-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.weak-tags span {
  padding: 4px 10px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 999px;
  color: var(--ink-soft, #d7d0c2);
  font-size: 12px;
}

.record-composer {
  display: grid;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid var(--line, #2c3a32);
}

.record-composer-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--muted, #a6b0a7);
}

.record-composer-head em {
  font-style: normal;
  color: var(--amber, #d7a64f);
}

.answer-box {
  width: 100%;
  min-height: 130px;
  padding: 12px 14px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 9px;
  background: #0b100e;
  color: var(--ink, #f2eee3);
  font-size: 14px;
  line-height: 1.7;
  resize: vertical;
}

.answer-box:focus {
  outline: 2px solid var(--amber, #d7a64f);
  outline-offset: 1px;
}

.record-composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 11px;
  color: var(--muted, #a6b0a7);
}

.finish {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line, #2c3a32);
}

.finish p {
  margin: 0;
  color: var(--muted, #a6b0a7);
  font-size: 12.5px;
}

.primary {
  padding: 9px 16px;
  border-radius: 9px;
  background: var(--amber, #d7a64f);
  color: #1b1b18;
  font-size: 13px;
  font-weight: 650;
  transition: background 0.15s ease, transform 0.15s ease;
}

.primary:hover {
  background: #c99b4f;
}

.primary:active {
  transform: translateY(1px) scale(0.99);
}

.primary:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .primary {
    transition: none;
  }
}

@media (max-width: 620px) {
  .record-head,
  .finish {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .record-composer-foot {
    align-items: stretch;
    flex-direction: column;
  }

  .record-composer-foot .primary {
    width: 100%;
  }
}
</style>
