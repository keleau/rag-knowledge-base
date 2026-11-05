<script setup lang="ts">
import type { AbilityStat } from '../learning'

defineProps<{
  stats: AbilityStat[]
  activeTag: string
  answered: number
  total: number
  busy: boolean
  steps: string[]
}>()

const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'more'): void
  (event: 'exam'): void
}>()
</script>

<template>
  <aside class="ability-rail" aria-label="能力进度">
    <header class="ability-head">
      <span>能力进度</span>
      <strong>{{ answered }}/{{ total }}</strong>
    </header>
    <div class="ability-list">
      <button
        v-for="stat in stats"
        :key="stat.id"
        type="button"
        class="ability-row"
        :class="{ active: stat.id === activeTag, complete: stat.total > 0 && stat.done === stat.total }"
        @click="emit('select', stat.id)"
      >
        <span class="ability-name">{{ stat.name }}</span>
        <span class="ability-count">{{ stat.done }}/{{ stat.total }}</span>
        <span class="ability-track"><i :style="{ width: `${stat.percent}%` }"></i></span>
        <span class="ability-meta">
          {{ stat.average === null ? '未自评' : `自评 ${stat.average}` }} · 目标 {{ stat.target }}
        </span>
      </button>
    </div>
    <div class="ability-actions">
      <button class="ghost" type="button" :disabled="busy" @click="emit('more')">
        {{ busy ? '生成中…' : '再来几道' }}
      </button>
      <button class="ghost" type="button" :disabled="busy || answered === 0" @click="emit('exam')">
        {{ busy ? '生成中…' : '生成模拟考' }}
      </button>
      <p v-if="steps.length" class="stream-note">{{ steps[steps.length - 1] }}</p>
    </div>
  </aside>
</template>

<style scoped>
.ability-rail {
  min-width: 0;
  padding-right: 16px;
  border-right: 1px solid var(--line, #2c3a32);
}

.ability-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, #2c3a32);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--muted, #a6b0a7);
}

.ability-head strong {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  font-weight: 500;
  color: var(--amber, #d7a64f);
}

.ability-list {
  display: grid;
  gap: 2px;
  padding: 8px 0;
}

.ability-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 8px;
  width: 100%;
  padding: 9px 8px;
  border-radius: 8px;
  color: var(--muted, #a6b0a7);
  text-align: left;
  transition: background 0.16s ease, color 0.16s ease;
}

.ability-row:hover {
  background: rgba(245, 242, 234, 0.045);
  color: var(--ink-soft, #d7d0c2);
}

.ability-row.active {
  background: rgba(245, 242, 234, 0.08);
  color: var(--cream, #f2eee3);
}

.ability-name {
  font-size: 13px;
  font-weight: 600;
}

.ability-count {
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
  color: var(--amber, #d7a64f);
}

.ability-track {
  grid-column: 1 / -1;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(245, 242, 234, 0.1);
}

.ability-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--amber, #d7a64f);
  transition: width 0.25s ease;
}

.ability-row.complete .ability-track i {
  background: #8fc9a9;
}

.ability-meta {
  grid-column: 1 / -1;
  font-size: 10.5px;
  color: var(--muted, #a6b0a7);
}

.ability-actions {
  display: grid;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--line, #2c3a32);
}

.stream-note {
  margin: 2px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--muted, #a6b0a7);
}

.ghost {
  padding: 8px 13px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 9px;
  color: var(--ink-soft, #d7d0c2);
  font-size: 13px;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.ghost:hover {
  border-color: var(--line-strong, #405146);
}

.ghost:active {
  transform: translateY(1px) scale(0.99);
}

.ghost:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .ability-row,
  .ability-track i,
  .ghost {
    transition: none;
  }
}

@media (max-width: 980px) {
  .ability-rail {
    padding-right: 0;
  }
}

@media (max-width: 700px) {
  .ability-rail {
    padding: 0 0 14px;
    border-right: 0;
    border-bottom: 1px solid var(--line, #2c3a32);
  }

  .ability-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ability-actions {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
