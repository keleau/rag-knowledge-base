<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import AssessmentWorkbench from './assessment/AssessmentWorkbench.vue'
import ChatView from './components/ChatView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import DocumentDrawer from './components/DocumentDrawer.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import Sidebar from './components/Sidebar.vue'
import ToastStack from './components/ToastStack.vue'
import { api } from './api'
import type {
  Conversation,
  ConversationSummary,
  DocumentDetail,
  DocumentSummary,
  Health,
  Source,
  Toast,
  ToastKind,
  TraceStep,
} from './types'
import { errorMessage, isAbortError } from './utils'

const health = ref<Health | null>(null)
const view = ref<'chat' | 'assessment'>('chat')
const workbench = ref<InstanceType<typeof AssessmentWorkbench> | null>(null)
const conversations = ref<ConversationSummary[]>([])
const documents = ref<DocumentSummary[]>([])
const activeId = ref<string | null>(null)
const activeConversation = ref<Conversation | null>(null)
const loadingConversation = ref(false)
const booting = ref(true)
const streaming = ref(false)
const streamContent = ref('')
const streamSources = ref<Source[]>([])
const streamTrace = ref<TraceStep[]>([])
const uploading = ref(false)
const drawerDoc = ref<DocumentDetail | null>(null)
const documentPanel = ref<{ openFilePicker: () => void } | null>(null)
const sidebarOpen = ref(false)
const docsOpen = ref(false)
const toasts = ref<Toast[]>([])
const confirmState = reactive({
  open: false,
  title: '',
  message: '',
  confirmLabel: '确认',
  danger: false,
  action: null as null | (() => Promise<void> | void),
})

let abortController: AbortController | null = null
let streamSequence = 0
let loadSequence = 0
let toastSequence = 0

function toSummary(conversation: Conversation): ConversationSummary {
  const last = conversation.messages[conversation.messages.length - 1]
  return {
    id: conversation.id,
    title: conversation.title,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    message_count: conversation.messages.length,
    preview: (last?.content || '').replace(/\s+/g, ' ').slice(0, 80),
  }
}

function notify(kind: ToastKind, message: string) {
  const id = ++toastSequence
  toasts.value.push({ id, kind, message })
  window.setTimeout(() => dismissToast(id), 4200)
}

function dismissToast(id: number) {
  toasts.value = toasts.value.filter((toast) => toast.id !== id)
}

async function refreshHealth() {
  try {
    health.value = await api.health()
  } catch {
    // Keep the last known state; individual actions surface their own errors.
  }
}

async function loadConversations() {
  try {
    conversations.value = (await api.listConversations()).conversations
  } catch (error) {
    notify('error', errorMessage(error))
  }
}

async function loadDocuments() {
  try {
    documents.value = (await api.listDocuments()).documents
  } catch (error) {
    notify('error', errorMessage(error))
  }
}

async function bootstrap() {
  try {
    health.value = await api.health()
  } catch (error) {
    notify('error', `无法连接后端：${errorMessage(error)}`)
    booting.value = false
    return
  }
  try {
    await Promise.all([loadConversations(), loadDocuments()])
    const saved = localStorage.getItem('zhiwen.assessment_id')
    if (saved) {
      view.value = 'assessment'
    } else if (conversations.value.length) {
      await selectConversation(conversations.value[0].id)
    }
  } finally {
    booting.value = false
  }
}

async function openAssessment() {
  sidebarOpen.value = false
  view.value = 'assessment'
  await nextTick()
  const saved = localStorage.getItem('zhiwen.assessment_id')
  if (saved) {
    await workbench.value?.load(saved)
  }
}

function exitAssessment() {
  view.value = 'chat'
  if (!activeConversation.value && conversations.value.length) {
    selectConversation(conversations.value[0].id)
  }
}

function cancelActiveStream() {
  streamSequence += 1
  abortController?.abort()
  abortController = null
  streaming.value = false
  streamContent.value = ''
  streamSources.value = []
  streamTrace.value = []
}

async function selectConversation(id: string) {
  view.value = 'chat'
  sidebarOpen.value = false
  if (activeId.value === id && activeConversation.value) return
  cancelActiveStream()
  const sequence = ++loadSequence
  activeId.value = id
  loadingConversation.value = true
  try {
    const conversation = await api.getConversation(id)
    if (sequence !== loadSequence) return
    activeConversation.value = conversation
  } catch (error) {
    if (sequence !== loadSequence) return
    notify('error', errorMessage(error))
    activeConversation.value = null
    activeId.value = null
    await loadConversations()
  } finally {
    if (sequence === loadSequence) loadingConversation.value = false
  }
}

async function newConversation() {
  view.value = 'chat'
  cancelActiveStream()
  try {
    const conversation = await api.createConversation()
    activeId.value = conversation.id
    activeConversation.value = conversation
    conversations.value.unshift(toSummary(conversation))
    sidebarOpen.value = false
  } catch (error) {
    notify('error', errorMessage(error))
  }
}

async function refreshActiveConversation(id: string) {
  if (activeId.value !== id) return
  try {
    activeConversation.value = await api.getConversation(id)
  } catch {
    // Keep the locally rendered messages if the conversation was removed.
  }
}

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

async function handleSend(content: string) {
  if (streaming.value) return
  let conversation = activeConversation.value
  if (!conversation) {
    try {
      conversation = await api.createConversation()
    } catch (error) {
      notify('error', errorMessage(error))
      return
    }
    activeId.value = conversation.id
    activeConversation.value = conversation
    conversations.value.unshift(toSummary(conversation))
  }

  const conversationId = conversation.id
  conversation.messages.push({
    id: `local-${Date.now()}`,
    role: 'user',
    content,
    created_at: new Date().toISOString(),
  })

  streaming.value = true
  streamContent.value = ''
  streamSources.value = []
  streamTrace.value = []
  const sequence = ++streamSequence
  const controller = new AbortController()
  abortController = controller

  try {
    await api.streamChat(
      conversationId,
      content,
      {
        onStep(step) {
          if (sequence !== streamSequence) return
          const index = streamTrace.value.findIndex((item) => item.id === step.id)
          if (index >= 0) streamTrace.value[index] = step
          else streamTrace.value.push(step)
        },
        onSources(sources) {
          if (sequence === streamSequence) streamSources.value = sources
        },
        onDelta(delta) {
          if (sequence === streamSequence) streamContent.value += delta
        },
        onDone(payload) {
          if (sequence !== streamSequence) return
          streamContent.value = payload.content
          if (payload.trace) streamTrace.value = payload.trace
        },
      },
      controller.signal,
    )
    if (sequence !== streamSequence) return
    await refreshActiveConversation(conversationId)
    await Promise.all([loadConversations(), refreshHealth()])
  } catch (error) {
    if (sequence !== streamSequence) return
    if (isAbortError(error)) {
      if (streamContent.value.trim() && activeConversation.value) {
        activeConversation.value.messages.push({
          id: `local-stop-${Date.now()}`,
          role: 'assistant',
          content: `${streamContent.value}\n\n（已停止生成）`,
          created_at: new Date().toISOString(),
          sources: streamSources.value.length ? [...streamSources.value] : undefined,
          trace: streamTrace.value.length ? [...streamTrace.value] : undefined,
        })
      }
      notify('info', '已停止生成')
      await loadConversations()
    } else {
      notify('error', errorMessage(error))
      await wait(150)
      await refreshActiveConversation(conversationId)
      await loadConversations()
    }
  } finally {
    if (sequence === streamSequence) {
      streaming.value = false
      streamContent.value = ''
      streamSources.value = []
      streamTrace.value = []
      abortController = null
    }
  }
}

function stopGeneration() {
  abortController?.abort()
}

async function renameActive(title: string) {
  const id = activeId.value
  if (!id) return
  try {
    const updated = await api.renameConversation(id, title)
    if (activeConversation.value) activeConversation.value.title = updated.title
    const summary = conversations.value.find((item) => item.id === id)
    if (summary) summary.title = updated.title
    await loadConversations()
  } catch (error) {
    notify('error', errorMessage(error))
  }
}

function openConfirm(options: {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  action: () => Promise<void> | void
}) {
  confirmState.open = true
  confirmState.title = options.title
  confirmState.message = options.message
  confirmState.confirmLabel = options.confirmLabel || '确认'
  confirmState.danger = options.danger ?? false
  confirmState.action = options.action
}

function closeConfirm() {
  confirmState.open = false
  confirmState.action = null
}

async function runConfirm() {
  const action = confirmState.action
  confirmState.open = false
  confirmState.action = null
  if (!action) return
  try {
    await action()
  } catch (error) {
    notify('error', errorMessage(error))
  }
}

function requestDeleteConversation(id: string) {
  const summary = conversations.value.find((item) => item.id === id)
  openConfirm({
    title: '删除这段对话？',
    message: `「${summary?.title || '该对话'}」中的所有消息将被永久删除，无法恢复。`,
    confirmLabel: '删除对话',
    danger: true,
    action: async () => {
      if (activeId.value === id) cancelActiveStream()
      await api.deleteConversation(id)
      conversations.value = conversations.value.filter((item) => item.id !== id)
      if (activeId.value === id) {
        activeId.value = null
        activeConversation.value = null
        const next = conversations.value[0]
        if (next) await selectConversation(next.id)
      }
      notify('success', '对话已删除')
    },
  })
}

async function uploadFiles(files: FileList) {
  const file = files.item(0)
  if (!file || uploading.value) return

  const extension = `.${(file.name.split('.').pop() || '').toLowerCase()}`
  const allowed = ['.txt', '.md', '.markdown', '.docx', '.pdf']
  if (!allowed.includes(extension)) {
    notify('error', '仅支持 TXT / Markdown / Word / PDF 文档')
    return
  }
  const maxMb = health.value?.max_upload_mb ?? 20
  if (file.size > maxMb * 1024 * 1024) {
    notify('error', `文件不能超过 ${maxMb} MB`)
    return
  }

  uploading.value = true
  try {
    const document = await api.uploadDocument(file)
    await Promise.all([loadDocuments(), refreshHealth()])
    notify(
      'success',
      `「${document.name}」已入库，切分为 ${document.chunk_count} 个分块`,
    )
  } catch (error) {
    notify('error', errorMessage(error))
  } finally {
    uploading.value = false
  }
}

function requestDeleteDocument(id: string) {
  const document = documents.value.find((item) => item.id === id)
  openConfirm({
    title: '删除这份文档？',
    message: `「${document?.name || '该文档'}」及其所有分块将从知识库移除，之后不再参与检索。`,
    confirmLabel: '删除文档',
    danger: true,
    action: async () => {
      await api.deleteDocument(id)
      if (drawerDoc.value?.id === id) drawerDoc.value = null
      await Promise.all([loadDocuments(), refreshHealth()])
      notify('success', '文档已删除')
    },
  })
}

async function openDocument(id: string) {
  docsOpen.value = false
  try {
    drawerDoc.value = await api.getDocument(id)
  } catch (error) {
    notify('error', errorMessage(error))
  }
}

function closeMobilePanels() {
  sidebarOpen.value = false
  docsOpen.value = false
}

function toggleDocs() {
  docsOpen.value = !docsOpen.value
}

function requestUpload() {
  if (window.matchMedia('(max-width: 1180px)').matches) {
    docsOpen.value = true
  }
  documentPanel.value?.openFilePicker()
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeMobilePanels()
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalKeydown)
  bootstrap().then(async () => {
    const requested = new URLSearchParams(window.location.search).get('assessment')
    if (requested) {
      view.value = 'assessment'
      await nextTick()
      await workbench.value?.load(requested)
    }
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  abortController?.abort()
})
</script>

<template>
  <div
    class="app-shell"
    :class="{ 'sidebar-open': sidebarOpen, 'docs-open': docsOpen, 'assessment-mode': view === 'assessment' }"
  >
    <Sidebar
      v-if="view === 'chat'"
      :conversations="conversations"
      :active-id="activeId"
      :health="health"
      :view="view"
      @new-chat="newConversation"
      @select="selectConversation"
      @delete="requestDeleteConversation"
      @close="sidebarOpen = false"
      @open-assessment="openAssessment"
    />

    <div
      v-if="sidebarOpen || docsOpen"
      class="mobile-backdrop"
      aria-hidden="true"
      @click="closeMobilePanels"
    ></div>

    <main class="main-column">
      <AssessmentWorkbench
        v-if="view === 'assessment'"
        ref="workbench"
        :notify="notify"
        @exit="exitAssessment"
      />
      <ChatView
        v-else
        :conversation="activeConversation"
        :health="health"
        :streaming="streaming"
        :stream-content="streamContent"
        :stream-sources="streamSources"
        :stream-trace="streamTrace"
        :loading="booting || loadingConversation"
        @send="handleSend"
        @stop="stopGeneration"
        @rename="renameActive"
        @open-document="openDocument"
        @toggle-sidebar="sidebarOpen = true"
        @toggle-docs="toggleDocs"
        @request-upload="requestUpload"
      />
    </main>

    <DocumentPanel
      v-if="view === 'chat'"
      ref="documentPanel"
      :documents="documents"
      :health="health"
      :uploading="uploading"
      @upload="uploadFiles"
      @delete="requestDeleteDocument"
      @open="openDocument"
      @close="docsOpen = false"
    />

    <DocumentDrawer
      v-if="drawerDoc"
      :doc="drawerDoc"
      :settings="health"
      @close="drawerDoc = null"
      @delete="requestDeleteDocument"
    />

    <ConfirmDialog
      :open="confirmState.open"
      :title="confirmState.title"
      :message="confirmState.message"
      :confirm-label="confirmState.confirmLabel"
      :danger="confirmState.danger"
      @confirm="runConfirm"
      @cancel="closeConfirm"
    />

    <ToastStack :toasts="toasts" @dismiss="dismissToast" />
  </div>
</template>
