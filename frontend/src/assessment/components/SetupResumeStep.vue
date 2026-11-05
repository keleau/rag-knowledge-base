<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '../../components/AppIcon.vue'
import SetupStep from './SetupStep.vue'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
  busy: string
  editingId: string | null
}>()

const editValue = defineModel<string>('editValue', { required: true })

const emit = defineEmits<{
  (event: 'upload-resume', files: FileList | null): void
  (event: 're-extract'): void
  (event: 'select-project', id: string): void
  (event: 'start-edit', id: string, summary: string | null): void
  (event: 'save-edit', id: string): void
}>()

const hasResume = computed(() => Boolean(props.detail.session.resume_document_id))
</script>

<template>
  <SetupStep
    :index="1"
    title="上传简历，识别项目"
  >
    <template #description>
      <p>txt / md / docx / pdf，发送给模型前会自动遮罩手机号、邮箱、身份证。</p>
    </template>

    <label class="setup-drop" :class="{ done: hasResume }">
      <AppIcon name="upload" :size="18" />
      <span>{{ hasResume ? '重新上传简历' : '选择或拖入简历文件' }}</span>
      <input
        type="file"
        accept=".txt,.md,.markdown,.docx,.pdf"
        hidden
        @change="emit('upload-resume', ($event.target as HTMLInputElement).files)"
      />
    </label>

    <div v-if="detail.projects.length" class="project-grid">
      <article
        v-for="item in detail.projects"
        :key="item.id"
        class="project-card"
        :class="{ selected: item.selected }"
        @click="emit('select-project', item.id)"
      >
        <header>
          <strong>{{ item.name }}</strong>
          <span v-if="item.period" class="project-period">{{ item.period }}</span>
        </header>
        <p v-if="editingId !== item.id" class="project-summary">{{ item.summary || '（无简介）' }}</p>
        <input
          v-else
          v-model="editValue"
          class="project-edit"
          @keydown.enter="emit('save-edit', item.id)"
          @blur="emit('save-edit', item.id)"
        />
        <p class="project-quote">识别依据：{{ item.source_quote }}</p>
        <button class="setup-link" type="button" @click.stop="emit('start-edit', item.id, item.summary)">
          {{ editingId === item.id ? '编辑中…' : '修改简介' }}
        </button>
      </article>
    </div>
    <p v-else-if="hasResume" class="hint">正在等待项目提取；如果失败，可以点下面的按钮重试。</p>
    <button
      v-if="hasResume"
      class="setup-ghost"
      type="button"
      :disabled="busy === 'extract'"
      @click="emit('re-extract')"
    >
      {{ busy === 'extract' ? '提取中…' : '重新提取项目' }}
    </button>
  </SetupStep>
</template>

<style scoped>
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.project-card {
  padding: 12px 14px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 12px;
  background: #141a16;
  cursor: pointer;
}

.project-card.selected {
  border-color: var(--amber, #d7a64f);
  box-shadow: inset 0 0 0 1px var(--amber, #d7a64f);
}

.project-card header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.project-period {
  color: var(--muted, #a6b0a7);
  font-size: 12px;
}

.project-summary,
.project-quote {
  margin: 0 0 6px;
  color: var(--ink-soft, #d7d0c2);
  font-size: 12.5px;
  line-height: 1.55;
}

.project-quote {
  color: var(--muted, #a6b0a7);
}

.project-edit {
  width: 100%;
  margin-bottom: 6px;
  padding: 6px 8px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 8px;
  background: #0b100e;
  color: var(--ink, #f2eee3);
}

.hint {
  margin-top: 10px;
  color: var(--muted, #a6b0a7);
  font-size: 12px;
}
</style>
