<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '../../components/AppIcon.vue'
import SetupStep from './SetupStep.vue'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
  busy: string
  docName: string
}>()

const emit = defineEmits<{
  (event: 'upload-doc', files: FileList | null): void
  (event: 'prepare'): void
}>()

const project = computed(() => props.detail.selected_project)
const hasDoc = computed(() => Boolean(props.detail.session.project_document_id))
</script>

<template>
  <SetupStep
    :index="2"
    title="项目介绍文档"
    :locked="!project"
  >
    <template #description>
      <p>至少 5 个分块；写得越具体，题目越像“照着你的项目问”。</p>
    </template>

    <label class="setup-drop" :class="{ done: hasDoc }" :aria-disabled="!project">
      <AppIcon name="doc" :size="18" />
      <span>{{ hasDoc ? (docName || '重新上传项目介绍') : '选择或拖入项目介绍（md / docx / pdf）' }}</span>
      <input
        type="file"
        accept=".txt,.md,.markdown,.docx,.pdf"
        hidden
        :disabled="!project"
        @change="emit('upload-doc', ($event.target as HTMLInputElement).files)"
      />
    </label>
    <button
      v-if="hasDoc"
      class="setup-ghost"
      type="button"
      :disabled="busy === 'prepare'"
      @click="emit('prepare')"
    >
      {{ busy === 'prepare' ? '生成中…' : '重新生成标签 / 能力目标 / 练习' }}
    </button>
  </SetupStep>
</template>
