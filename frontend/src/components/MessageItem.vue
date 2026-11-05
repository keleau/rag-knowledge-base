<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import AgentTrace from './AgentTrace.vue'
import AppIcon from './AppIcon.vue'
import type { Message } from '../types'
import { formatTime } from '../utils'

marked.setOptions({ gfm: true, breaks: true })

const props = defineProps<{
  message: Message
  streaming?: boolean
}>()

const emit = defineEmits<{
  (event: 'open-document', id: string): void
}>()

const sources = computed(() => props.message.sources || [])
const trace = computed(() => props.message.trace || [])
const sourcesOpen = ref(false)
const sourcesEl = ref<HTMLElement | null>(null)
const copied = ref(false)
let copyTimer: number | undefined

watch(sourcesOpen, async (open) => {
  if (!open) return
  await nextTick()
  sourcesEl.value?.scrollIntoView({
    block: 'nearest',
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
  })
})

const rendered = computed(() => {
  if (props.message.role !== 'assistant' || !props.message.content) return ''
  const html = marked.parse(props.message.content, { async: false }) as string
  return DOMPurify.sanitize(html)
})

const thinkingLabel = computed(() => {
  const last = trace.value[trace.value.length - 1]
  if (last) return last.summary || last.label
  return sources.value.length
    ? `已检索到 ${sources.value.length} 条资料，正在组织回答…`
    : '正在规划检索步骤…'
})

function sourceExcerpt(text: string): string {
  const cleaned = text
    .split('\n')
    .filter((line) => !/^\s*#{1,6}\s/.test(line))
    .join('\n')
    .replace(/\n{2,}/g, '\n')
    .trim()
  return cleaned || text.trim()
}

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copied.value = true
    window.clearTimeout(copyTimer)
    copyTimer = window.setTimeout(() => {
      copied.value = false
    }, 1600)
  } catch {
    // Clipboard may be unavailable on insecure origins.
  }
}

onBeforeUnmount(() => window.clearTimeout(copyTimer))
</script>

<template>
  <article class="message" :class="message.role">
    <div v-if="message.role === 'assistant'" class="assistant-avatar" aria-hidden="true">知</div>
    <div class="message-body">
      <template v-if="message.role === 'user'">
        <div class="user-bubble">{{ message.content }}</div>
        <p class="user-time">{{ formatTime(message.created_at) }}</p>
      </template>

      <template v-else>
        <AgentTrace v-if="trace.length" :steps="trace" :streaming="streaming" />

        <div class="assistant-content" :class="{ 'is-streaming': streaming }">
          <div v-if="message.content" class="markdown" v-html="rendered"></div>
          <div v-else class="thinking">
            <span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span>
            <span>{{ thinkingLabel }}</span>
          </div>

          <div v-if="sources.length" ref="sourcesEl" class="sources">
            <button
              class="sources-toggle"
              type="button"
              :aria-expanded="sourcesOpen"
              @click="sourcesOpen = !sourcesOpen"
            >
              <AppIcon name="library" :size="14" />
              <span>参考来源 {{ sources.length }}</span>
              <AppIcon name="chevron" :size="13" class="chevron" :class="{ open: sourcesOpen }" />
            </button>
            <Transition name="sources">
              <ol v-if="sourcesOpen" class="source-list">
                <li v-for="(source, index) in sources" :key="source.chunk_id">
                  <button
                    type="button"
                    class="source-card"
                    :title="sourceExcerpt(source.text)"
                    @click="emit('open-document', source.document_id)"
                  >
                    <span class="source-index">[{{ index + 1 }}]</span>
                    <span class="source-content">
                      <span class="source-head">
                        <strong>{{ source.document_name }}</strong>
                        <span v-if="typeof source.score === 'number'">
                          第 {{ source.chunk_index + 1 }} 块 · 相关度
                          {{ Math.min(99, Math.round(source.score * 100)) }}%
                        </span>
                        <span v-else>第 {{ source.chunk_index + 1 }} 块 · 工具读取</span>
                      </span>
                      <span class="source-snippet">{{ sourceExcerpt(source.text) }}</span>
                    </span>
                  </button>
                </li>
              </ol>
            </Transition>
          </div>

          <footer class="message-foot">
            <span>{{ formatTime(message.created_at) }}</span>
            <span v-if="trace.length">{{ trace.length }} 个步骤</span>
            <button
              v-if="message.content && !streaming"
              type="button"
              class="copy-btn"
              @click="copyContent"
            >
              <AppIcon name="copy" :size="12" />
              {{ copied ? '已复制' : '复制' }}
            </button>
          </footer>
        </div>
      </template>
    </div>
  </article>
</template>
