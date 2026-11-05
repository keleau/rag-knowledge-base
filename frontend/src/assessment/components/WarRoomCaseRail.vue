<script setup lang="ts">
import type { Probe } from '../probes'

defineProps<{
  projectName: string
  caseMeta: string
  tagCount: number
  entityCount: number
  practiceCount: number
  probes: Probe[]
  stageHint: string
  primaryLabel: string
  primaryTone: 'primary' | 'secondary'
  busy: boolean
}>()

const emit = defineEmits<{
  (event: 'primary'): void
}>()
</script>

<template>
  <aside class="case-rail" aria-label="项目档案">
    <div class="case-scroll">
      <section class="case-file">
        <span class="case-kicker">项目档案</span>
        <h1>{{ projectName }}</h1>
        <p class="case-meta">{{ caseMeta }}</p>
        <div class="case-stats">
          <div><strong>{{ tagCount }}</strong><span>能力</span></div>
          <div><strong>{{ entityCount }}</strong><span>证据</span></div>
          <div><strong>{{ practiceCount }}</strong><span>练习</span></div>
        </div>
      </section>

      <section class="probe-block">
        <header>
          <span>面试官可能追问</span>
          <em>{{ probes.length }}/3</em>
        </header>
        <div v-if="probes.length" class="probe-list">
          <article
            v-for="(probe, index) in probes"
            :key="`${probe.tag}-${index}`"
            class="probe-card"
            :class="`tone-${probe.tone}`"
            :style="{ animationDelay: `${index * 60}ms` }"
          >
            <span class="probe-index">{{ probe.index }}</span>
            <div class="probe-copy">
              <strong>{{ probe.question }}</strong>
              <p>{{ probe.reason }}</p>
              <span class="probe-status">{{ probe.status }}</span>
            </div>
          </article>
        </div>
        <div v-else class="probe-empty">
          <p>还没有足够的项目证据。</p>
          <span>上传简历、项目介绍和可选代码后，这里会自动出现 3 个最可能被追问的点。</span>
        </div>
      </section>
    </div>

    <div class="case-footer">
      <div class="rail-action">
        <p>{{ stageHint }}</p>
        <button
          class="primary rail-primary"
          :class="{ 'rail-secondary': primaryTone === 'secondary' }"
          type="button"
          :disabled="busy"
          @click="emit('primary')"
        >
          {{ primaryLabel }}
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.case-rail {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--forest, #16211d);
  color: var(--cream, #f2eee3);
  border-right: 1px solid rgba(245, 242, 234, 0.12);
}

.case-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 22px 20px 16px;
}

.case-file {
  padding-bottom: 18px;
  border-bottom: 1px solid rgba(245, 242, 234, 0.16);
}

.case-kicker {
  font-family: var(--font-sans, sans-serif);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(245, 242, 234, 0.55);
}

.case-file h1 {
  margin: 8px 0 6px;
  font-family: var(--font-serif, serif);
  font-size: 26px;
  line-height: 1.2;
  font-weight: 600;
  overflow-wrap: anywhere;
  color: var(--cream, #f2eee3);
}

.case-meta {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(245, 242, 234, 0.68);
}

.case-stats {
  display: flex;
  gap: 18px;
  margin-top: 16px;
}

.case-stats div {
  display: grid;
  gap: 2px;
}

.case-stats strong {
  font-family: var(--font-mono, monospace);
  font-size: 18px;
  font-weight: 500;
  color: var(--cream, #f2eee3);
}

.case-stats span {
  font-size: 11px;
  color: rgba(245, 242, 234, 0.55);
}

.probe-block {
  display: grid;
  gap: 10px;
}

.probe-block > header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  color: rgba(245, 242, 234, 0.62);
  font-size: 11px;
  letter-spacing: 0.06em;
}

.probe-block > header em {
  font-family: var(--font-mono, monospace);
  font-style: normal;
  color: var(--amber, #d7a64f);
}

.probe-list {
  display: grid;
  gap: 8px;
}

.probe-card {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 9px;
  padding: 10px;
  border: 1px solid rgba(245, 242, 234, 0.14);
  border-radius: 10px;
  background: rgba(245, 242, 234, 0.055);
  animation: probe-in 0.4s both;
}

.probe-index {
  padding-top: 2px;
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  color: var(--amber, #d7a64f);
}

.probe-copy strong {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  font-size: 13px;
  line-height: 1.5;
  font-weight: 600;
  color: var(--cream, #f2eee3);
}

.probe-copy p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  margin: 4px 0 8px;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(245, 242, 234, 0.68);
}

.probe-status {
  display: inline-block;
  padding-bottom: 1px;
  border-bottom: 1px solid currentColor;
  font-size: 10px;
  letter-spacing: 0.06em;
}

.tone-gap .probe-status {
  color: #e2a08e;
}

.tone-watch .probe-status {
  color: var(--amber, #d7a64f);
}

.tone-covered .probe-status {
  color: #8fc9a9;
}

.probe-empty {
  padding: 14px;
  border: 1px dashed rgba(245, 242, 234, 0.22);
  border-radius: 10px;
  color: rgba(245, 242, 234, 0.68);
  font-size: 13px;
  line-height: 1.6;
}

.probe-empty p {
  margin: 0 0 4px;
  color: var(--cream, #f2eee3);
  font-size: 13px;
}

.case-footer {
  flex: none;
  display: grid;
  gap: 12px;
  padding: 14px 20px 18px;
  border-top: 1px solid rgba(245, 242, 234, 0.16);
  background: var(--forest, #16211d);
}

.rail-action {
  display: grid;
  gap: 10px;
}

.rail-action p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(245, 242, 234, 0.68);
}

.primary {
  padding: 11px 16px;
  border-radius: 9px;
  background: var(--amber, #d7a64f);
  color: #1b1b18;
  font-size: 13px;
  font-weight: 650;
  transition: background 0.15s ease, transform 0.15s ease;
}

.primary:hover {
  background: #c99b4f;
}

.primary:active {
  transform: translateY(1px) scale(0.99);
}

.rail-primary {
  width: 100%;
}

.rail-secondary {
  background: transparent;
  color: var(--ink-soft, #d7d0c2);
  border: 1px solid var(--line-strong, #405146);
}

.rail-secondary:hover {
  background: rgba(245, 242, 234, 0.06);
  border-color: var(--muted, #a6b0a7);
}

@keyframes probe-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .probe-card,
  .primary {
    animation: none;
    transition: none;
  }
}

@media (max-width: 900px) {
  .case-rail {
    display: block;
    overflow: visible;
    border-right: 0;
    border-bottom: 1px solid rgba(245, 242, 234, 0.16);
  }

  .case-scroll {
    display: flex;
    flex: none;
    flex-direction: column;
    overflow: visible;
    gap: 18px;
    min-height: auto;
    padding: 16px;
  }

  .probe-list {
    grid-auto-flow: row;
    grid-auto-columns: auto;
    overflow: visible;
    padding-bottom: 0;
  }

  .case-footer {
    display: block;
    padding: 0 16px 16px;
  }
}
</style>
