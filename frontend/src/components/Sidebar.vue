<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import type { ConversationSummary, Health } from '../types'
import { formatRelative } from '../utils'

const props = defineProps<{
  conversations: ConversationSummary[]
  activeId: string | null
  health: Health | null
  view?: 'chat' | 'assessment'
}>()
const emit = defineEmits<{
  (event: 'new-chat'): void
  (event: 'select', id: string): void
  (event: 'delete', id: string): void
  (event: 'close'): void
  (event: 'open-assessment'): void
}>()

const query = ref('')
const filtered = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return props.conversations
  return props.conversations.filter(
    (item) =>
      item.title.toLowerCase().includes(term) || item.preview.toLowerCase().includes(term),
  )
})
</script>

<template>
  <aside class="sidebar" aria-label="会话侧栏">
    <div class="sidebar-head">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><span>知</span></div>
        <div class="brand-text">
          <p class="brand-name">知问</p>
          <p class="brand-sub">RAG KNOWLEDGE</p>
        </div>
      </div>
      <button class="icon-btn sidebar-close" aria-label="关闭会话侧栏" @click="emit('close')">
        <AppIcon name="close" :size="17" />
      </button>
    </div>

    <button class="assessment-btn" :class="{ active: view === 'assessment' }" type="button" @click="emit('open-assessment')">
      <AppIcon name="spark" :size="16" />
      <span>项目答辩训练</span>
    </button>

    <button class="new-chat-btn" @click="emit('new-chat')">
      <span class="new-chat-icon"><AppIcon name="plus" :size="16" /></span>
      <span>新建对话</span>
    </button>

    <label class="conversation-search">
      <AppIcon name="search" :size="15" />
      <input v-model="query" type="search" placeholder="搜索对话" aria-label="搜索对话" />
    </label>

    <nav class="conversation-list" aria-label="对话列表">
      <p class="list-label"><span>最近对话</span><span>{{ filtered.length }}</span></p>
      <div
        v-for="item in filtered"
        :key="item.id"
        class="conversation-item"
        :class="{ active: item.id === activeId }"
      >
        <button
          class="conv-select"
          :aria-current="item.id === activeId ? 'page' : undefined"
          @click="emit('select', item.id)"
        >
          <span class="conv-title">{{ item.title }}</span>
          <span class="conv-preview">{{ item.preview || '还没有消息' }}</span>
          <span class="conv-time">{{ formatRelative(item.updated_at) }}</span>
        </button>
        <button
          class="conv-delete"
          :aria-label="`删除对话：${item.title}`"
          @click.stop="emit('delete', item.id)"
        >
          <AppIcon name="trash" :size="14" />
        </button>
      </div>
      <p v-if="!filtered.length" class="sidebar-empty">
        {{ query ? '没有匹配的对话' : '还没有对话，开始第一次提问吧。' }}
      </p>
    </nav>

    <div class="sidebar-foot">
      <div class="status-row">
        <span class="status-dot" :class="{ 'is-demo': health?.demo_mode }"></span>
        <span>{{ health ? (health.demo_mode ? '本地演示模式' : health.llm_mode === 'replay' ? '回放评测模式' : 'DeepSeek 模式') : '连接中…' }}</span>
      </div>
      <div class="status-stats">
        <span>{{ health?.documents ?? 0 }} 篇文档</span>
        <span>·</span>
        <span>{{ health?.chunks ?? 0 }} 个分块</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.assessment-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0 10px;
  padding: 9px 12px;
  border: 1px solid rgba(232, 176, 75, 0.35);
  border-radius: 10px;
  background: rgba(232, 176, 75, 0.07);
  color: #e8b04b;
  font-size: 13px;
  cursor: pointer;
}
.assessment-btn.active {
  background: rgba(232, 176, 75, 0.16);
  border-color: #e8b04b;
}
</style>
