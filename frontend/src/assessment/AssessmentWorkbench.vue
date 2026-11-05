<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import AppIcon from './../components/AppIcon.vue'
import { errorMessage } from '../utils'
import { assessmentApi } from './api'
import ExamPage from './pages/ExamPage.vue'
import GradingPage from './pages/GradingPage.vue'
import InterviewPage from './pages/InterviewPage.vue'
import LearningPage from './pages/LearningPage.vue'
import RepeatPage from './pages/RepeatPage.vue'
import ReportPage from './pages/ReportPage.vue'
import SetupPage from './pages/SetupPage.vue'
import WarRoomCaseRail from './components/WarRoomCaseRail.vue'
import WarRoomMissionStrip from './components/WarRoomMissionStrip.vue'
import { MISSION_STAGES, missionForStage, type MissionKey } from './mission'
import { buildProbes } from './probes'
import type { AssessmentDetail, Stage } from './types'

const props = defineProps<{
  notify: (kind: 'success' | 'error' | 'info', message: string) => void
}>()

const emit = defineEmits<{
  (event: 'exit'): void
}>()

const detail = ref<AssessmentDetail | null>(null)
const loading = ref(false)
const codeContent = ref<string | null>(null)
const viewOverride = ref<Stage | null>(null)
const busy = ref(false)
const workspaceRef = ref<HTMLElement | null>(null)

const storageKey = 'zhiwen.assessment_id'
const stage = computed<Stage>(() => viewOverride.value || detail.value?.session.stage || 'setup')
const missionKey = computed<MissionKey>(() => missionForStage(stage.value))
const groupIndex = computed(() =>
  Math.max(0, MISSION_STAGES.findIndex((item) => item.key === missionKey.value)),
)
const probes = computed(() => (detail.value ? buildProbes(detail.value) : []))

const stageLabel = computed(
  () =>
    ({
      setup: '情报收集',
      learning: '演练',
      exam: '模拟考',
      grading: '阅卷',
      interview: '实战',
      report: '复盘',
      practice: '复练',
      done: '完成',
    })[stage.value] || '情报收集',
)
const stageTitle = computed(
  () =>
    ({
      setup: '建立项目档案',
      learning: '按能力演练',
      exam: '闭卷模拟考',
      grading: '证据阅卷',
      interview: '薄弱点实战',
      report: '答辩复盘',
      practice: '针对性复练',
      done: '本轮完成',
    })[stage.value] || '建立项目档案',
)
const stageHint = computed(
  () =>
    ({
      setup: '先把简历、项目和证据收齐，后面所有题都从这里长出来。',
      learning: '一次只练一个能力，答完再自评，不用刷题数量证明自己。',
      exam: '不看提示，按真实面试的节奏把这张卷答完。',
      grading: '分数只是线索，证据缺口才是下一步。',
      interview: '只追薄弱点，答不清会继续追问。',
      report: '把“还差什么”变成下一轮动作。',
      practice: '只练没达标的能力，练完再判一次。',
      done: '这一轮已经完成，可以查看复盘或再练一轮。',
    })[stage.value] || '',
)
const projectName = computed(
  () => detail.value?.selected_project?.name || detail.value?.session.title || '项目档案',
)
const caseMeta = computed(() => {
  const project = detail.value?.selected_project
  const parts = [project?.role, project?.period].filter(Boolean)
  return parts.length ? parts.join(' · ') : '项目角色与周期待补充'
})
const modeLabel = computed(() => {
  const mode = detail.value?.llm_mode
  if (mode === 'llm') return '实时模型'
  if (mode === 'replay') return '录制回放'
  return '本地演示'
})

const primaryAction = computed<{
  label: string
  action: () => void | Promise<void>
  tone: 'primary' | 'secondary'
}>(() => {
  if (!detail.value) return { label: '建立第一份项目档案', action: createSession, tone: 'primary' }
  switch (stage.value) {
    case 'setup':
      return { label: '继续准备', action: focusWorkspace, tone: 'secondary' }
    case 'learning':
      return { label: '继续演练', action: focusWorkspace, tone: 'secondary' }
    case 'exam':
      return { label: '继续答题', action: focusWorkspace, tone: 'secondary' }
    case 'grading':
      return { label: '开始模拟面试', action: toInterview, tone: 'primary' }
    case 'interview':
      return { label: '继续面试', action: focusWorkspace, tone: 'secondary' }
    case 'report':
    case 'practice':
    default:
      return { label: '查看复盘', action: focusWorkspace, tone: 'secondary' }
  }
})

function focusWorkspace() {
  if (window.innerWidth <= 900) {
    workspaceRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  workspaceRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

async function openStage(key: MissionKey) {
  const target = MISSION_STAGES.findIndex((item) => item.key === key)
  if (target < 0 || target > groupIndex.value) return
  if (key === 'setup') viewOverride.value = 'setup'
  else if (key === 'learning') viewOverride.value = 'learning'
  else if (key === 'exam') viewOverride.value = stage.value === 'grading' ? 'grading' : 'exam'
  else if (key === 'interview') viewOverride.value = 'interview'
  else viewOverride.value = stage.value === 'practice' ? 'practice' : 'report'
  await nextTick()
  if (window.innerWidth <= 900) {
    workspaceRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

async function load(id: string) {
  loading.value = true
  try {
    detail.value = await assessmentApi.get(id)
    localStorage.setItem(storageKey, id)
    await loadCodeContent(id)
    viewOverride.value = null
  } catch (error) {
    props.notify('error', errorMessage(error))
    localStorage.removeItem(storageKey)
    detail.value = null
  } finally {
    loading.value = false
  }
}

async function loadCodeContent(id: string) {
  codeContent.value = null
  try {
    const payload = await assessmentApi.getCodeContent(id)
    codeContent.value = payload.content || null
  } catch {
    codeContent.value = null
  }
}

async function refresh() {
  if (!detail.value) return
  try {
    detail.value = await assessmentApi.get(detail.value.session.id)
    localStorage.setItem(storageKey, detail.value.session.id)
  } catch (error) {
    props.notify('error', errorMessage(error))
  }
}

async function createSession() {
  if (busy.value) return
  busy.value = true
  try {
    const session = await assessmentApi.create('项目答辩练习')
    await load(session.id)
  } catch (error) {
    props.notify('error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function enterLearning() {
  if (!detail.value) return
  await refresh()
  if (detail.value?.session.stage === 'setup') {
    try {
      await assessmentApi.advance(detail.value.session.id, 'learning', detail.value.session.version)
      await refresh()
    } catch (error) {
      props.notify('error', errorMessage(error))
      return
    }
  }
  viewOverride.value = 'learning'
}

async function toExam() {
  await refresh()
  viewOverride.value = 'exam'
}

async function toGrading() {
  await refresh()
  viewOverride.value = 'grading'
}

async function toInterview() {
  if (!detail.value) return
  try {
    if (detail.value.session.stage === 'grading') {
      await assessmentApi.startInterview(detail.value.session.id, detail.value.session.version)
    }
  } catch (error) {
    props.notify('error', errorMessage(error))
  }
  await refresh()
  viewOverride.value = 'interview'
}

async function toReport() {
  await refresh()
  viewOverride.value = 'report'
}

async function startRepeat() {
  if (!detail.value || busy.value) return
  busy.value = true
  const controller = new AbortController()
  try {
    await assessmentApi.startRepeat(
      detail.value.session.id,
      detail.value.session.version,
      (event, data) => {
        if (event === 'step') props.notify('info', String((data as unknown as { summary?: string }).summary || ''))
      },
      controller.signal,
    )
    await refresh()
    viewOverride.value = 'practice'
  } catch (error) {
    props.notify('error', errorMessage(error))
  } finally {
    busy.value = false
  }
}

function exit() {
  emit('exit')
}

defineExpose({ load, createSession })
</script>

<template>
  <div class="war-room">
    <header class="war-top">
      <button class="war-back" type="button" @click="exit">
        <AppIcon name="arrow" :size="15" /> 返回知问
      </button>
      <div class="war-title">
        <span class="war-kicker">知问 · 项目训练</span>
        <strong>答辩作战室</strong>
      </div>
      <div class="war-tools">
        <span v-if="detail" class="war-mode">{{ modeLabel }}</span>
        <button class="war-new" type="button" :disabled="busy" @click="createSession">新建评估</button>
      </div>
    </header>

    <WarRoomMissionStrip v-if="detail" :group-index="groupIndex" @select="openStage" />

    <section v-if="!detail && !loading" class="war-empty">
      <span class="war-kicker">还没有项目档案</span>
      <h1>把项目练到能扛住追问。</h1>
      <p>
        上传简历和项目介绍，系统会整理出面试官最可能追问的 3 个点，再带你演练、模拟考和实战。
      </p>
      <button class="primary" type="button" :disabled="busy" @click="createSession">
        {{ busy ? '建立中…' : '建立第一份项目档案' }}
      </button>
    </section>

    <p v-if="loading" class="war-loading">正在打开项目档案…</p>

    <div v-if="detail" class="war-body">
      <WarRoomCaseRail
        :project-name="projectName"
        :case-meta="caseMeta"
        :tag-count="detail.tags.length"
        :entity-count="detail.entities.length"
        :practice-count="detail.practice.count"
        :probes="probes"
        :stage-hint="stageHint"
        :primary-label="primaryAction.label"
        :primary-tone="primaryAction.tone"
        :busy="busy"
        @primary="primaryAction.action"
      />

      <section ref="workspaceRef" class="war-workspace">
        <header class="workspace-head">
          <div>
            <h2>{{ stageTitle }}</h2>
            <p>{{ stageHint }}</p>
          </div>
          <span class="workspace-count">
            {{ detail.practice.count }} 练 · {{ detail.exam.questions.length }} 考 · {{ detail.interview.turns.length }} 面
          </span>
        </header>

        <Transition name="stage" mode="out-in">
          <div :key="stage" class="workspace-panel">
            <SetupPage
              v-if="stage === 'setup'"
              :detail="detail"
              @changed="refresh"
              @notify="notify"
              @enter-learning="enterLearning"
            />
            <LearningPage
              v-else-if="stage === 'learning'"
              :detail="detail"
              :code-content="codeContent"
              @changed="refresh"
              @notify="notify"
              @enter-exam="toExam"
            />
            <ExamPage
              v-else-if="stage === 'exam'"
              :detail="detail"
              :code-content="codeContent"
              @changed="refresh"
              @notify="notify"
              @submitted="toGrading"
            />
            <GradingPage
              v-else-if="stage === 'grading'"
              :detail="detail"
              @changed="refresh"
              @notify="notify"
              @next="toInterview"
            />
            <InterviewPage
              v-else-if="stage === 'interview'"
              :detail="detail"
              @changed="refresh"
              @notify="notify"
              @report="toReport"
            />
            <RepeatPage
              v-else-if="stage === 'practice'"
              :detail="detail"
              @changed="refresh"
              @notify="notify"
              @report="toReport"
            />
            <ReportPage
              v-else-if="stage === 'report'"
              :detail="detail"
              @repeat="startRepeat"
            />
          </div>
        </Transition>
      </section>
    </div>
  </div>
</template>

<style scoped>
.war-room {
  --paper: #101513;
  --paper-deep: #0d1210;
  --surface: #151b17;
  --surface-2: #1b231e;
  --ink: #f2eee3;
  --ink-soft: #d7d0c2;
  --line: #2c3a32;
  --line-strong: #405146;
  --muted: #a6b0a7;
  --muted-2: #87938a;
  --accent: #e8b04b;
  --accent-deep: #c99b4f;
  --accent-soft: #2b3329;
  --amber: #d7a64f;
  --danger: #d97b63;
  --cream: #f2eee3;
  --panel: #171d19;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--paper-deep);
  color: var(--ink);
}

.war-top {
  flex: none;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 13px 24px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}

.war-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  color: var(--muted);
  font-size: 13px;
  transition: color 0.15s ease;
}

.war-back:hover {
  color: var(--ink);
}

.war-title {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 1px;
}

.war-kicker {
  font-family: var(--font-sans, sans-serif);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.war-title strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-serif, serif);
  font-size: 17px;
  font-weight: 600;
}

.war-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

.war-mode {
  color: var(--muted);
  font-size: 11px;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px 9px;
}

.war-new {
  color: var(--ink-soft);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 13px;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.war-new:hover {
  background: var(--surface-2);
  border-color: var(--line-strong);
}

.war-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
}

.war-workspace {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 26px 30px 64px;
  background: var(--paper-deep);
  scroll-behavior: smooth;
}

.workspace-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  max-width: 1040px;
  margin: 0 auto 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.workspace-head h2 {
  margin: 0 0 4px;
  font-family: var(--font-serif, serif);
  font-size: 25px;
  line-height: 1.25;
  font-weight: 600;
}

.workspace-head p {
  margin: 0;
  max-width: 60ch;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.workspace-count {
  flex: none;
  white-space: nowrap;
  padding: 4px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
}

.workspace-panel {
  max-width: 1040px;
  margin: 0 auto;
}

:deep(.step-block.locked) {
  opacity: 0.82;
}

:deep(.your-answer) {
  max-width: 72ch;
  line-height: 1.65;
  color: var(--ink-soft);
  background: #121713;
}

:deep(.weak-item) {
  border-left: 0;
  padding-left: 0;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}

:deep(.weak-item:first-of-type) {
  padding-top: 0;
  border-top: 0;
}

:deep(.grading-page .score-top .primary) {
  background: transparent;
  color: var(--ink-soft);
  border: 1px solid var(--line-strong);
}

.war-empty {
  flex: 1;
  display: grid;
  place-content: center;
  justify-items: start;
  gap: 12px;
  width: min(760px, 100%);
  padding: 8vh 8vw;
}

.war-empty h1 {
  margin: 0;
  font-family: var(--font-serif, serif);
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.war-empty p {
  margin: 0;
  max-width: 46ch;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.7;
}

.primary {
  padding: 11px 16px;
  border-radius: 9px;
  background: var(--amber);
  color: #1b1b18;
  font-size: 13px;
  font-weight: 650;
  transition: background 0.15s ease, transform 0.15s ease;
}

.primary:hover {
  background: var(--accent-deep);
}

.primary:active {
  transform: translateY(1px) scale(0.99);
}

.war-empty .primary {
  margin-top: 8px;
}

.war-loading {
  padding: 8vh 8vw;
  color: var(--muted);
}

.stage-enter-active,
.stage-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.stage-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.stage-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (prefers-reduced-motion: reduce) {
  .war-new,
  .war-back,
  .primary,
  .stage-enter-active,
  .stage-leave-active {
    transition: none;
  }
}

@media (max-width: 1180px) {
  .war-body {
    grid-template-columns: 280px minmax(0, 1fr);
  }

  .war-workspace {
    padding: 22px 22px 56px;
  }
}

@media (max-width: 900px) {
  .war-top {
    flex-wrap: wrap;
    gap: 10px 14px;
    padding: 12px 16px;
  }

  .war-title {
    order: 3;
    flex-basis: 100%;
  }

  .war-body {
    display: block;
    overflow-y: auto;
  }

  .war-workspace {
    overflow: visible;
    padding: 18px 16px 48px;
  }

  .workspace-head {
    flex-direction: column;
    gap: 8px;
  }

  .workspace-count {
    align-self: flex-start;
  }

  :deep(.grading-page .score-top) {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 10px 14px;
  }

  :deep(.grading-page .score-meta) {
    grid-column: 1 / -1;
  }

  :deep(.grading-page .score-meta p) {
    line-height: 1.6;
  }

  :deep(.grading-page .score-top .primary) {
    grid-column: 1 / -1;
    justify-self: start;
  }
}

@media (max-width: 560px) {
  .war-title strong {
    font-size: 16px;
  }

  .war-mode {
    display: none;
  }

  .workspace-head h2 {
    font-size: 22px;
  }
}
</style>
