<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import type { TraceStep } from '../types'

const props = defineProps<{
  steps: TraceStep[]
  streaming?: boolean
}>()

const open = ref(Boolean(props.streaming))
watch(
  () => props.streaming,
  (value) => {
    if (value) open.value = true
  },
)

function isCheck(step: TraceStep): boolean {
  return step.kind === 'check' || step.name === 'agent_check' || step.name === 'citation_check'
}

const toolCount = computed(() => props.steps.filter((step) => !isCheck(step)).length)
const errorCount = computed(() => props.steps.filter((step) => step.status === 'error').length)
const totalMs = computed(() =>
  props.steps.reduce((sum, step) => sum + (step.duration_ms || 0), 0),
)

const headline = computed(() => {
  const parts = [`${toolCount.value} 次工具调用`]
  if (totalMs.value >= 1000) parts.push(`${(totalMs.value / 1000).toFixed(1)}s`)
  else if (totalMs.value > 0) parts.push(`${totalMs.value}ms`)
  if (errorCount.value) parts.push(`${errorCount.value} 个降级`)
  return parts.join(' · ')
})

function iconFor(step: TraceStep): string {
  if (step.status === 'error') return 'alert'
  if (isCheck(step)) return step.name === 'citation_check' ? 'check' : 'info'
  if (step.name === 'search_knowledge') return 'search'
  if (step.name === 'list_documents') return 'library'
  if (step.name === 'get_document_chunks') return 'doc'
  return 'spark'
}

function argChips(step: TraceStep): string[] {
  const args = step.args || {}
  const chips: string[] = []
  if (typeof args.query === 'string' && args.query.trim()) chips.push(`query: ${args.query}`)
  if (typeof args.document_name === 'string') chips.push(`文档: ${args.document_name}`)
  else if (typeof args.document_id === 'string') chips.push(`id: ${args.document_id.slice(0, 8)}`)
  if (typeof args.top_k === 'number') chips.push(`top_k: ${args.top_k}`)
  return chips
}
</script>

<template>
  <section class="agent-trace" :class="{ 'is-live': streaming }" aria-label="Agent 工具轨迹">
    <button
      type="button"
      class="trace-toggle"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="trace-spark" aria-hidden="true"><AppIcon name="spark" :size="13" /></span>
      <span class="trace-title">工具轨迹</span>
      <span class="trace-meta">{{ headline }}</span>
      <AppIcon name="chevron" :size="13" class="chevron" :class="{ open }" />
    </button>

    <Transition name="trace">
      <ol v-if="open" class="trace-list">
        <li
          v-for="(step, index) in steps"
          :key="step.id"
          class="trace-step"
          :class="[step.status, { check: isCheck(step) }]"
        >
          <span class="trace-rail" aria-hidden="true"><i class="trace-dot"></i></span>
          <div class="trace-body">
            <div class="trace-line">
              <span class="trace-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <AppIcon :name="iconFor(step)" :size="13" class="trace-icon" />
              <strong class="trace-label">{{ step.label }}</strong>
              <span v-if="!isCheck(step)" class="trace-tool">{{ step.name }}</span>
              <span v-if="step.duration_ms" class="trace-duration">{{ step.duration_ms }}ms</span>
            </div>
            <p class="trace-summary">{{ step.summary }}</p>
            <div v-if="argChips(step).length" class="trace-args">
              <code v-for="chip in argChips(step)" :key="chip">{{ chip }}</code>
            </div>
          </div>
        </li>
      </ol>
    </Transition>
  </section>
</template>
