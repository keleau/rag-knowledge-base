<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import type { DocumentSummary, Health } from '../types'
import { extensionOf, formatBytes } from '../utils'

const props = defineProps<{
  documents: DocumentSummary[]
  health: Health | null
  uploading: boolean
}>()

const emit = defineEmits<{
  (event: 'upload', files: FileList): void
  (event: 'delete', id: string): void
  (event: 'open', id: string): void
  (event: 'close'): void
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)

function pickFile() {
  if (!props.uploading) fileInput.value?.click()
}

function onChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) emit('upload', input.files)
  input.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  const files = event.dataTransfer?.files
  if (files?.length) emit('upload', files)
}

defineExpose({ openFilePicker: pickFile })
</script>

<template>
  <aside class="docs-panel" aria-label="知识库文档">
    <div class="docs-head">
      <div>
        <p class="docs-eyebrow">LIBRARY</p>
        <h2>知识库</h2>
      </div>
      <div class="docs-head-actions">
        <span class="docs-count">{{ documents.length }}</span>
        <button class="icon-btn docs-close" aria-label="关闭知识库面板" @click="emit('close')">
          <AppIcon name="close" :size="17" />
        </button>
      </div>
    </div>

    <input
      ref="fileInput"
      class="sr-only"
      type="file"
      accept=".txt,.md,.markdown,.docx,.pdf"
      @change="onChange"
    />
    <div
      class="upload-zone"
      :class="{ dragging, busy: uploading }"
      role="button"
      tabindex="0"
      @click="pickFile"
      @keydown.enter="pickFile"
      @keydown.space.prevent="pickFile"
      @dragenter.prevent="dragging = true"
      @dragover.prevent
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <span class="upload-icon" :class="{ spinning: uploading }">
        <AppIcon :name="uploading ? 'spark' : 'upload'" :size="20" />
      </span>
      <p class="upload-title">{{ uploading ? '正在解析并建立索引…' : '上传文档' }}</p>
      <p class="upload-hint">拖拽到此处，或点击选择文件</p>
      <p class="upload-formats">
        TXT · MD · DOCX · PDF，单文件 ≤ {{ health?.max_upload_mb ?? 20 }} MB
      </p>
    </div>

    <div class="docs-list-head">
      <span>已入库文档</span>
      <span>{{ documents.length }} 份</span>
    </div>

    <div class="docs-list">
      <article v-for="document in documents" :key="document.id" class="doc-card">
        <button class="doc-open" :title="document.name" @click="emit('open', document.id)">
          <span class="doc-ext" :data-ext="extensionOf(document.name)">
            {{ extensionOf(document.name) }}
          </span>
          <span class="doc-info">
            <span class="doc-name">{{ document.name }}</span>
            <span class="doc-meta">
              {{ document.chunk_count }} 个分块 · {{ formatBytes(document.size) }}
            </span>
          </span>
        </button>
        <div class="doc-actions">
          <button
            class="icon-btn"
            :aria-label="`查看文档：${document.name}`"
            @click="emit('open', document.id)"
          >
            <AppIcon name="eye" :size="15" />
          </button>
          <button
            class="icon-btn danger"
            :aria-label="`删除文档：${document.name}`"
            @click="emit('delete', document.id)"
          >
            <AppIcon name="trash" :size="15" />
          </button>
        </div>
      </article>

      <div v-if="!documents.length" class="docs-empty">
        <span class="docs-empty-icon"><AppIcon name="library" :size="24" /></span>
        <p>知识库还是空的</p>
        <span>上传第一份文档，让回答有据可依。</span>
      </div>
    </div>

    <div class="docs-foot">
      <span>切片 {{ health?.chunk_size ?? 500 }} 字 / 块 · 重叠 {{ health?.chunk_overlap ?? 80 }} 字</span>
      <span>TOP {{ health?.top_k ?? 4 }}</span>
    </div>
  </aside>
</template>
