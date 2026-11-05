<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from '../../components/AppIcon.vue'
import { errorMessage } from '../../utils'
import { assessmentApi } from '../api'
import SetupStep from './SetupStep.vue'
import type { ProjectCode } from '../types'

const props = defineProps<{
  sessionId: string
  code: ProjectCode | null
  locked: boolean
}>()

const emit = defineEmits<{
  (event: 'changed'): void
  (event: 'notify', kind: 'success' | 'error' | 'info', message: string): void
}>()

const busy = ref(false)
const codeExpanded = ref(false)
const codeFileName = ref('App.vue')
const codeContent = ref('')
const codeResult = ref<{
  symbol_count: number
  symbols: Array<{ name: string; kind: string; line: number }>
} | null>(null)
const codeDragging = ref(false)

function readCodeFile(files: FileList | null) {
  const file = files?.item(0)
  if (!file) return
  if (file.size > 200 * 1024) {
    emit('notify', 'error', '代码文件不能超过 200 KB')
    return
  }
  codeFileName.value = file.name
  const reader = new FileReader()
  reader.onload = () => {
    codeContent.value = String(reader.result || '')
  }
  reader.readAsText(file, 'utf-8')
}

function onDrop(event: DragEvent) {
  codeDragging.value = false
  readCodeFile(event.dataTransfer?.files || null)
}

async function submitCode() {
  if (!codeContent.value.trim() || busy.value) return
  busy.value = true
  try {
    const result = await assessmentApi.uploadCode(props.sessionId, codeFileName.value, codeContent.value)
    codeResult.value = { symbol_count: result.symbol_count, symbols: result.symbols }
    emit('changed')
    emit('notify', 'success', `代码已解析，识别到 ${result.symbol_count} 个符号`)
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function removeCode() {
  try {
    await assessmentApi.deleteCode(props.sessionId)
    codeResult.value = null
    codeContent.value = ''
    emit('changed')
  } catch (error) {
    emit('notify', 'error', errorMessage(error))
  }
}

function resetCodeForm() {
  codeExpanded.value = true
  codeContent.value = ''
  codeFileName.value = 'App.vue'
  codeResult.value = null
}
</script>

<template>
  <SetupStep
    :index="3"
    title="页面代码（可选）"
    :locked="locked"
  >
    <template #description>
      <p>粘贴或上传一个 <code>.vue / .ts / .js</code> 文件，系统会出“这个功能是怎么实现的”这类代码题。</p>
    </template>

    <div v-if="props.code && !codeExpanded" class="code-summary">
      <AppIcon name="check" :size="16" />
      <div>
        <strong>{{ props.code.file_name }}</strong>
        <span>{{ props.code.line_count }} 行 · {{ props.code.symbols.length }} 个符号</span>
      </div>
      <button class="setup-ghost small" type="button" @click="resetCodeForm">替换</button>
      <button class="setup-ghost small danger" type="button" @click="removeCode">移除</button>
    </div>

    <div v-if="!props.code || codeExpanded" class="code-form">
      <input v-model="codeFileName" class="code-name" placeholder="App.vue" />
      <textarea
        v-model="codeContent"
        class="code-text"
        spellcheck="false"
        placeholder="把页面代码粘贴到这里，或者拖入 .vue/.ts/.js 文件（≤200 KB）"
        @dragover.prevent="codeDragging = true"
        @dragleave.prevent="codeDragging = false"
        @drop.prevent="onDrop"
        :class="{ dragging: codeDragging }"
      ></textarea>
      <label class="code-file">
        选择文件
        <input
          type="file"
          accept=".vue,.ts,.js"
          hidden
          @change="readCodeFile(($event.target as HTMLInputElement).files)"
        />
      </label>
      <div class="code-actions">
        <button class="setup-primary" type="button" :disabled="!codeContent.trim() || busy" @click="submitCode">
          {{ busy ? '解析中…' : '解析代码' }}
        </button>
        <button v-if="props.code" class="setup-ghost small" type="button" @click="codeExpanded = false">
          取消
        </button>
      </div>
    </div>

    <div v-if="codeResult" class="code-result">
      <p>识别到 {{ codeResult.symbol_count }} 个符号：</p>
      <div class="symbol-chips">
        <span v-for="symbol in codeResult.symbols" :key="`${symbol.name}-${symbol.line}`" class="symbol-chip">
          {{ symbol.name }}<em>{{ symbol.kind }} · L{{ symbol.line }}</em>
        </span>
      </div>
    </div>
  </SetupStep>
</template>

<style scoped>
.code-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid rgba(143, 201, 169, 0.45);
  border-radius: 12px;
}

.code-summary div {
  display: grid;
  flex: 1;
}

.code-summary span {
  color: var(--muted, #a6b0a7);
  font-size: 12px;
}

.code-form {
  display: grid;
  gap: 10px;
}

.code-name {
  padding: 8px 12px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 10px;
  background: #0b100e;
  color: var(--ink, #f2eee3);
  font-family: var(--font-mono, monospace);
}

.code-text {
  min-height: 220px;
  padding: 12px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 10px;
  background: #0b100e;
  color: var(--ink-soft, #d7d0c2);
  font-family: var(--font-mono, monospace);
  font-size: 12.5px;
  line-height: 1.55;
  resize: vertical;
}

.code-text.dragging {
  border-color: var(--amber, #d7a64f);
}

.code-file {
  justify-self: start;
  color: #9ec7ff;
  font-size: 12px;
  cursor: pointer;
}

.code-actions {
  display: flex;
  gap: 10px;
}

.code-result p {
  margin: 8px 0;
  color: var(--muted, #a6b0a7);
  font-size: 12px;
}

.symbol-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.symbol-chip {
  padding: 2px 9px;
  border: 1px solid rgba(158, 199, 255, 0.35);
  border-radius: 999px;
  color: #9ec7ff;
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}

.symbol-chip em {
  margin-left: 4px;
  color: #aab4c2;
  font-style: normal;
}
</style>
