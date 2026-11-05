<script setup lang="ts">
import type { InterviewTurn } from '../types'

defineProps<{
  turns: InterviewTurn[]
}>()

function turnState(turn: InterviewTurn): string {
  if (turn.status === 'asking') return '待回答'
  if (turn.score !== null) return '已评分'
  return '已记录'
}

function followUpOf(turns: InterviewTurn[], turnId: string | null): string {
  if (!turnId) return ''
  const index = turns.findIndex((item) => item.id === turnId)
  return index >= 0 ? `追问自第 ${index + 1} 条` : '追问'
}
</script>

<template>
  <div class="record">
    <article
      v-for="(turn, index) in turns"
      :key="turn.id"
      class="record-entry"
      :class="{ follow: turn.follow_up_of, asking: turn.status === 'asking' }"
    >
      <div class="record-index">
        <span>{{ String(index + 1).padStart(2, '0') }}</span>
        <i></i>
      </div>
      <div class="record-body">
        <header class="entry-head">
          <span class="entry-tag">{{ turn.tag }}</span>
          <span v-if="turn.follow_up_of" class="follow-flag">{{ followUpOf(turns, turn.follow_up_of) }}</span>
          <span class="entry-state">{{ turnState(turn) }}</span>
        </header>

        <p class="record-question">
          <span class="speaker">面试官</span>
          {{ turn.question }}
        </p>

        <div v-if="turn.answer" class="record-answer">
          <span class="speaker">你</span>
          <p>{{ turn.answer }}</p>
        </div>

        <div v-if="turn.score !== null" class="record-score">
          <span class="score-value">{{ turn.score }}<small>/10</small></span>
          <ul v-if="turn.evidence.length" class="hits">
            <li v-for="(hit, hitIndex) in turn.evidence" :key="hitIndex" :class="{ miss: !hit.hit }">
              {{ hit.hit ? '✓' : '✗' }} {{ hit.point }}
            </li>
          </ul>
        </div>
        <p v-else-if="turn.status === 'asking'" class="waiting">等待你的回答…</p>
      </div>
    </article>
  </div>
</template>

<style scoped>
.record {
  display: grid;
}

.record-entry {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr);
  gap: 12px;
}

.record-entry.follow .record-body {
  margin-left: 16px;
  padding-left: 14px;
  border-left: 1px solid rgba(215, 166, 79, 0.35);
}

.record-index {
  display: grid;
  grid-template-rows: auto 1fr;
  justify-items: center;
  gap: 6px;
  padding-top: 3px;
}

.record-index span {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--amber, #d7a64f);
}

.record-index i {
  width: 1px;
  min-height: 28px;
  background: var(--line, #2c3a32);
}

.record-entry:last-child .record-index i {
  display: none;
}

.record-body {
  display: grid;
  gap: 8px;
  padding: 0 0 22px;
}

.entry-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--muted, #a6b0a7);
}

.entry-tag {
  color: var(--amber, #d7a64f);
}

.follow-flag {
  padding: 1px 7px;
  border: 1px solid rgba(217, 123, 99, 0.55);
  border-radius: 999px;
  color: var(--danger, #d97b63);
  font-size: 10px;
}

.entry-state {
  margin-left: auto;
  color: var(--muted-2, #87938a);
}

.record-entry.asking .entry-state {
  color: var(--amber, #d7a64f);
}

.record-question {
  margin: 0;
  font-family: var(--font-serif, serif);
  font-size: 17px;
  line-height: 1.55;
  color: var(--ink, #f2eee3);
}

.speaker {
  display: inline-block;
  margin-right: 8px;
  font-family: var(--font-sans, sans-serif);
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--muted, #a6b0a7);
  vertical-align: 1px;
}

.record-answer {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 9px;
  background: #0b100e;
}

.record-answer .speaker {
  margin: 0;
  color: #8fc9a9;
}

.record-answer p {
  margin: 0;
  color: var(--ink-soft, #d7d0c2);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.record-score {
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.score-value {
  font-family: var(--font-mono, monospace);
  font-size: 17px;
  color: var(--ink, #f2eee3);
}

.score-value small {
  font-size: 10px;
  color: var(--muted, #a6b0a7);
}

.hits {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 11.5px;
  color: #8fc9a9;
}

.hits .miss {
  color: var(--danger, #d97b63);
}

.waiting {
  margin: 0;
  font-size: 12px;
  color: var(--amber, #d7a64f);
}

@media (max-width: 620px) {
  .record-entry {
    grid-template-columns: 30px minmax(0, 1fr);
    gap: 8px;
  }

  .record-entry.follow .record-body {
    margin-left: 8px;
    padding-left: 10px;
  }

  .record-question {
    font-size: 15.5px;
  }

  .record-answer {
    grid-template-columns: 1fr;
  }
}
</style>
