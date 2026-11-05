<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { api } from '../api'
import type { DocumentDetail, Health } from '../types'
import { extensionOf, formatBytes } from '../utils'

const props = defineProps<{
  doc: DocumentDetail
  settings: Health | null
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'delete', id: string): void
}>()

const closeButton = ref<HTMLButtonElement | null>(null)
const downloadUrl = computed(() => api.downloadDocumentUrl(props.doc.id))

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  document.body.classList.add('no-scroll')
  nextTick(() => closeButton.value?.focus())
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.body.classList.remove('no-scroll')
})
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div class="drawer-backdrop" @click.self="emit('close')">
        <aside
          class="doc-drawer"
          role="dialog"
          aria-modal="true"
          aria-labelledby="doc-drawer-title"
        >
          <header class="drawer-head">
            <div class="drawer-head-main">
              <span class="doc-ext large" :data-ext="extensionOf(doc.name)">
                {{ extensionOf(doc.name) }}
              </span>
              <div class="drawer-title-wrap">
                <p class="drawer-eyebrow">DOCUMENT</p>
                <h2 id="doc-drawer-title">{{ doc.name }}</h2>
              </div>
            </div>
            <button
              ref="closeButton"
              class="icon-btn"
              aria-label="关闭文档预览"
              @click="emit('close')"
            >
              <AppIcon name="close" :size="18" />
            </button>
          </header>

          <div class="drawer-meta">
            <span>{{ doc.chunk_count }} 个分块</span>
            <span>{{ doc.char_count }} 字符</span>
            <span>{{ formatBytes(doc.size) }}</span>
          </div>

          <div class="drawer-actions">
            <a class="ghost-btn" :href="downloadUrl" rel="noopener">
              <AppIcon name="download" :size="15" />
              下载原文
            </a>
            <button class="ghost-btn danger" @click="emit('delete', doc.id)">
              <AppIcon name="trash" :size="15" />
              删除文档
            </button>
          </div>

          <p class="drawer-note">
            当前切片：{{ settings?.chunk_size ?? 500 }} 字 / 块，相邻重叠
            {{ settings?.chunk_overlap ?? 80 }} 字。分块越小定位越精准，越大上下文越完整。
          </p>

          <div class="chunk-list">
            <article v-for="chunk in doc.chunks" :key="chunk.id" class="chunk-card">
              <header>
                <span>#{{ String(chunk.index + 1).padStart(2, '0') }}</span>
                <span>{{ chunk.text.length }} 字</span>
              </header>
              <p>{{ chunk.text }}</p>
            </article>
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>
