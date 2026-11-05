<script setup lang="ts">
import { computed, ref } from 'vue'
import { errorMessage } from '../../utils'
import { assessmentApi } from '../api'
import CapabilityPanel from '../components/CapabilityPanel.vue'
import EntityDebugPanel from '../components/EntityDebugPanel.vue'
import SetupCodeStep from '../components/SetupCodeStep.vue'
import SetupEnterStep from '../components/SetupEnterStep.vue'
import SetupProjectDocStep from '../components/SetupProjectDocStep.vue'
import SetupResumeStep from '../components/SetupResumeStep.vue'
import type { AssessmentDetail, Capability } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'notify', kind: 'success' | 'error' | 'info', message: string): void
  (event: 'enter-learning'): void
}>()

const busy = ref<string>('')
const steps = ref<Array<{ label: string; summary: string; rejected?: Array<{ prompt: string; reason: string }> }>>([])
const editing = ref<string | null>(null)
const editValue = ref('')
const docName = ref('')

const session = computed(() => props.detail.session)
const project = computed(() => props.detail.selected_project)
const busyLabel = computed(() => {
  return {
    resume: '上传简历中…',
    extract: '提取项目中…',
    doc: '上传项目介绍中…',
    prepare: '生成标签、能力目标和练习中…',
  }[busy.value] || ''
})

function forwardNotify(kind: 'success' | 'error' | 'info', message: string) {
  emit('notify', kind, message)
}

function onEvent(event: string, data: Record<string, unknown>) {
  if (event === 'step') {
    const payload = data as unknown as {
      label?: string
      summary?: string
      rejected?: Array<{ prompt: string; reason: string }>
    }
    steps.value.push({ label: payload.label || '处理中', summary: payload.summary || '', rejected: payload.rejected })
  }
}

async function uploadResume(files: FileList | null) {
  const file = files?.item(0)
  if (!file || busy.value) return
  busy.value = 'resume'
  try {
    await assessmentApi.uploadResume(session.value.id, file)
    emit('notify', 'success', '简历已上传，正在提取项目')
    await extractProjects()
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = busy.value === 'resume' ? '' : busy.value
  }
}

async function extractProjects() {
  steps.value = []
  busy.value = 'extract'
  const controller = new AbortController()
  try {
    await assessmentApi.extractProjects(session.value.id, onEvent, controller.signal)
    emit('changed')
    emit('notify', 'success', '项目列表已提取，可以手动修正')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = ''
  }
}

async function selectProject(projectId: string) {
  try {
    await assessmentApi.selectProject(session.value.id, projectId)
    emit('changed')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  }
}

function startEdit(name: string, summary: string | null) {
  editing.value = name
  editValue.value = summary || ''
}

async function saveEdit(projectId: string) {
  try {
    await assessmentApi.patchProject(projectId, { summary: editValue.value })
    editing.value = null
    emit('changed')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  }
}

async function uploadDoc(files: FileList | null) {
  const file = files?.item(0)
  if (!file || busy.value) return
  docName.value = file.name
  busy.value = 'doc'
  try {
    const result = await assessmentApi.uploadProjectDocument(session.value.id, file)
    emit('notify', 'success', `项目介绍已上传，切分为 ${result.document.chunk_count} 个分块`)
    await prepare()
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    if (busy.value === 'doc') busy.value = ''
  }
}

const EVENT_LABELS: Record<string, string> = {
  '项目文档': '1/5 生成标签与能力目标',
  '能力目标': '2/5 生成能力目标',
  '练习题': '3/5 生成练习题',
  '出题': '4/5 生成试卷',
  '复练': '5/5 生成复练题',
}

function friendlyStep(label: string): string {
  const match = Object.keys(EVENT_LABELS).find((key) => label.includes(key))
  return match ? EVENT_LABELS[match] : label
}

async function prepare() {
  steps.value = []
  busy.value = 'prepare'
  const controller = new AbortController()
  try {
    await assessmentApi.prepare(session.value.id, session.value.version, onEvent, controller.signal)
    emit('changed')
    emit('notify', 'success', '标签、能力目标和练习题已生成')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = ''
  }
}

async function changeTarget(capability: Capability, level: string) {
  try {
    await assessmentApi.patchCapability(capability.id, level)
    emit('changed')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  }
}
</script>

<template>
  <div class="setup-page">
    <SetupResumeStep
      :detail="detail"
      :busy="busy"
      :editing-id="editing"
      v-model:edit-value="editValue"
      @upload-resume="uploadResume"
      @re-extract="extractProjects"
      @select-project="selectProject"
      @start-edit="startEdit"
      @save-edit="saveEdit"
    />

    <SetupProjectDocStep
      :detail="detail"
      :busy="busy"
      :doc-name="docName"
      @upload-doc="uploadDoc"
      @prepare="prepare"
    />

    <section v-if="busy" class="setup-busy">
      <span class="setup-spinner"></span>
      <span>{{ busyLabel }}</span>
      <span class="setup-busy-hint">首次生成 20 道练习和标签通常需要 30–90 秒，请不要关闭页面</span>
    </section>

    <SetupCodeStep
      :session-id="session.id"
      :code="detail.code"
      :locked="!project"
      @changed="emit('changed')"
      @notify="forwardNotify"
    />

    <section v-if="steps.length" class="setup-stream">
      <p v-for="(step, index) in steps" :key="index" class="setup-stream-step">
        <span class="setup-stream-dot"></span>
        <span><strong>{{ friendlyStep(step.label) }}</strong> · {{ step.summary }}</span>
      </p>
    </section>

    <CapabilityPanel
      v-if="detail.capabilities.length"
      :capabilities="detail.capabilities"
      editable
      @change-target="changeTarget"
    />

    <EntityDebugPanel v-if="detail.entities.length" :detail="detail" />

    <SetupEnterStep :detail="detail" @enter-learning="emit('enter-learning')" />
  </div>
</template>

<style scoped>
.setup-page {
  display: grid;
  gap: 18px;
}

.setup-busy {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border: 1px solid rgba(215, 166, 79, 0.35);
  border-radius: 12px;
  background: rgba(215, 166, 79, 0.07);
  color: var(--amber, #d7a64f);
  font-size: 13px;
}

.setup-busy-hint {
  color: var(--muted, #a6b0a7);
  font-size: 12px;
}

.setup-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(215, 166, 79, 0.25);
  border-top-color: var(--amber, #d7a64f);
  border-radius: 50%;
  animation: setup-spin 0.8s linear infinite;
}

.setup-stream {
  display: grid;
  gap: 6px;
  padding: 12px 16px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 12px;
}

.setup-stream-step {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  color: var(--ink-soft, #d7d0c2);
  font-size: 12.5px;
}

.setup-stream-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--amber, #d7a64f);
}

@keyframes setup-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
