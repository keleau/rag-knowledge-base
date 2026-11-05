<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import MessageItem from './MessageItem.vue'
import type { Conversation, Health, Message, Source, TraceStep } from '../types'

const props = defineProps<{
  conversation: Conversation | null
  health: Health | null
  streaming: boolean
  streamContent: string
  streamSources: Source[]
  streamTrace: TraceStep[]
  loading: boolean
}>()

const emit = defineEmits<{
  (event: 'send', content: string): void
  (event: 'stop'): void
  (event: 'rename', title: string): void
  (event: 'open-document', id: string): void
  (event: 'toggle-sidebar'): void
  (event: 'toggle-docs'): void
  (event: 'request-upload'): void
}>()

const draft = ref('')
const composer = ref<HTMLTextAreaElement | null>(null)
const scrollEl = ref<HTMLDivElement | null>(null)
const nearBottom = ref(true)

const editingTitle = ref(false)
const titleDraft = ref('')
const titleInput = ref<HTMLInputElement | null>(null)

const hasDocuments = computed(() => (props.health?.documents || 0) > 0)
const hasMessages = computed(() => Boolean(props.conversation?.messages.length))
const showEmpty = computed(() => !props.loading && !props.streaming && !hasMessages.value)

const suggestions = [
  {
    label: '总结核心内容',
    text: '请总结当前知识库的核心内容，并标注引用来源。',
  },
  {
    label: '产品概述',
    text: '智能健康手表的产品概述是什么？',
  },
  {
    label: '适用人群',
    text: '这份文档适合哪些人使用？',
  },
]

const streamingMessage = computed<Message>(() => ({
  id: 'streaming',
  role: 'assistant',
  content: props.streamContent,
  created_at: new Date().toISOString(),
  sources: props.streamSources.length ? props.streamSources : undefined,
  trace: props.streamTrace.length ? props.streamTrace : undefined,
}))

function startTitleEdit() {
  if (!props.conversation) return
  titleDraft.value = props.conversation.title
  editingTitle.value = true
  nextTick(() => {
    titleInput.value?.focus()
    titleInput.value?.select()
  })
}

function commitTitle() {
  if (!editingTitle.value) return
  editingTitle.value = false
  const title = titleDraft.value.trim()
  if (title && title !== props.conversation?.title) emit('rename', title)
}

function cancelTitle() {
  editingTitle.value = false
}

function autoGrow() {
  const element = composer.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 180)}px`
}

function submit() {
  const content = draft.value.trim()
  if (!content || props.streaming || props.loading) return
  emit('send', content)
  draft.value = ''
  nextTick(autoGrow)
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}

function useSuggestion(text: string) {
  if (!hasDocuments.value) {
    emit('toggle-docs')
    return
  }
  emit('send', text)
}

function onScroll() {
  const element = scrollEl.value
  if (!element) return
  nearBottom.value = element.scrollHeight - element.scrollTop - element.clientHeight < 160
}

function scrollToBottom(force = false) {
  nextTick(() => {
    const element = scrollEl.value
    if (element && (force || nearBottom.value)) element.scrollTop = element.scrollHeight
  })
}

watch(
  () => props.conversation?.id,
  () => {
    editingTitle.value = false
    nearBottom.value = true
    scrollToBottom(true)
  },
)

watch(
  () => [props.conversation?.messages.length, props.streamContent, props.streaming],
  () => scrollToBottom(),
)

watch(
  () => props.loading,
  (loading) => {
    if (!loading) {
      nearBottom.value = true
      scrollToBottom(true)
    }
  },
)
</script>

<template>
  <section class="chat-view" aria-label="对话区">
    <header class="chat-header">
      <button
        class="icon-btn mobile-menu"
        aria-label="打开会话侧栏"
        @click="emit('toggle-sidebar')"
      >
        <AppIcon name="menu" :size="19" />
      </button>

      <div class="chat-heading">
        <div class="title-line">
          <input
            v-if="editingTitle"
            ref="titleInput"
            v-model="titleDraft"
            class="title-input"
            maxlength="60"
            aria-label="对话标题"
            @keydown.enter.prevent="commitTitle"
            @keydown.esc.prevent="cancelTitle"
            @blur="commitTitle"
          />
          <h1 v-else class="chat-title" @dblclick="startTitleEdit">
            {{ conversation?.title || '新对话' }}
          </h1>
          <button
            v-if="conversation"
            class="icon-btn title-edit"
            aria-label="重命名对话"
            @click="startTitleEdit"
          >
            <AppIcon name="edit" :size="14" />
          </button>
        </div>
        <p class="chat-sub">
          <span class="model-pill">{{ health?.demo_mode ? 'LOCAL DEMO' : health?.model || 'DEEPSEEK' }}</span>
          <span class="sub-dot">·</span>
          <span>Agent 工具检索</span>
          <span class="sub-dot">·</span>
          <span>最多 {{ health?.agent_max_steps ?? 4 }} 步</span>
        </p>
      </div>

      <button
        class="icon-btn mobile-docs"
        aria-label="打开知识库"
        @click="emit('toggle-docs')"
      >
        <AppIcon name="library" :size="19" />
        <span v-if="health?.documents" class="mini-badge">{{ health.documents }}</span>
      </button>
    </header>

    <div ref="scrollEl" class="messages-scroll" @scroll.passive="onScroll">
      <div class="messages-inner">
        <div v-if="loading" class="conversation-loading">
          <span class="spinner" aria-hidden="true"></span>
          <p>正在载入对话…</p>
        </div>

        <template v-else>
          <MessageItem
            v-for="message in conversation?.messages || []"
            :key="message.id"
            :message="message"
            @open-document="emit('open-document', $event)"
          />

          <MessageItem
            v-if="streaming"
            :message="streamingMessage"
            streaming
            @open-document="emit('open-document', $event)"
          />

          <div v-if="showEmpty" class="empty-state">
            <div class="empty-mark" aria-hidden="true"><span>知</span></div>
            <p class="empty-eyebrow">TOOL-CALLING RETRIEVAL AGENT</p>
            <h2>把文档，变成<br />可追问的知识。</h2>
            <p class="empty-copy">
              上传资料后，知问会自主规划检索步骤、调用知识库工具、核对引用依据；没有依据时会明确拒答。
            </p>

            <div v-if="hasDocuments" class="suggestions">
              <button
                v-for="suggestion in suggestions"
                :key="suggestion.label"
                class="suggestion"
                @click="useSuggestion(suggestion.text)"
              >
                <span class="suggestion-label">{{ suggestion.label }}</span>
                <span class="suggestion-text">{{ suggestion.text }}</span>
                <AppIcon name="arrow" :size="14" class="suggestion-arrow" />
              </button>
            </div>
            <div v-else class="empty-cta">
              <button class="primary-btn" @click="emit('request-upload')">
                <AppIcon name="upload" :size="16" />
                上传第一份文档
              </button>
              <p>支持 TXT / Markdown / Word / PDF</p>
            </div>

            <div v-if="health" class="empty-stats">
              <span>{{ health.documents }} 篇文档</span>
              <span>{{ health.chunks }} 个分块</span>
              <span>{{ health.demo_mode ? '本地演示模式' : 'DeepSeek 模式' }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="composer-wrap">
      <div class="composer" :class="{ 'is-busy': streaming }">
        <textarea
          ref="composer"
          v-model="draft"
          class="composer-input"
          rows="1"
          maxlength="8000"
          placeholder="输入问题，知问会先检索知识库…"
          aria-label="输入问题"
          :disabled="loading"
          @input="autoGrow"
          @keydown="onComposerKeydown"
        ></textarea>
        <div class="composer-actions">
          <span class="composer-hint">Enter 发送 · Shift + Enter 换行</span>
          <button
            v-if="streaming"
            class="send-btn stop"
            aria-label="停止生成"
            @click="emit('stop')"
          >
            <AppIcon name="stop" :size="15" />
          </button>
          <button
            v-else
            class="send-btn"
            :disabled="!draft.trim() || loading"
            aria-label="发送问题"
            @click="submit"
          >
            <AppIcon name="send" :size="17" />
          </button>
        </div>
      </div>
      <p class="composer-foot">回答基于知识库检索结果 · 请核对引用来源</p>
    </div>

    <p class="sr-only" aria-live="polite">{{ streaming ? '正在生成回答' : '' }}</p>
  </section>
</template>
