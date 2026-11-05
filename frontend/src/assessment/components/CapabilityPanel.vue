<script setup lang="ts">
import { levelLabel } from '../ui'
import type { Capability } from '../types'

defineProps<{
  capabilities: Capability[]
  editable?: boolean
}>()

const emit = defineEmits<{
  (event: 'change-target', capability: Capability, level: string): void
}>()

const levels = ['L1', 'L2', 'L3', 'L4']
</script>

<template>
  <section class="cap-panel">
    <header class="cap-head">
      <h3>能力目标</h3>
      <p>达到目标才算“能扛住这个项目的面试追问”。</p>
    </header>
    <ul v-if="capabilities.length" class="cap-list">
      <li v-for="cap in capabilities" :key="cap.id" class="cap-item">
        <div class="cap-row">
          <span class="cap-tag">{{ cap.tag }}</span>
          <span class="cap-levels">
            <button
              v-for="level in levels"
              :key="level"
              type="button"
              class="cap-level"
              :class="{ active: cap.target_level === level, disabled: !editable }"
              :disabled="!editable"
              @click="emit('change-target', cap, level)"
            >
              {{ level }}
            </button>
          </span>
          <span class="cap-status" :class="{ met: cap.met, over: cap.current_level && levels.indexOf(cap.current_level) > levels.indexOf(cap.target_level) }">
            {{ cap.current_level ? `当前 ${levelLabel(cap.current_level)}` : '未覆盖' }}
          </span>
        </div>
        <ul v-if="cap.acceptance.length" class="cap-acceptance">
          <li v-for="(item, index) in cap.acceptance" :key="index">{{ item }}</li>
        </ul>
      </li>
    </ul>
    <p v-else class="cap-empty">生成项目文档后，这里会出现 6 条能力目标。</p>
  </section>
</template>

<style scoped>
.cap-panel {
  border: 1px solid var(--line, #2c2f36);
  border-radius: 14px;
  padding: 16px 18px;
  background: var(--panel, #17191f);
}
.cap-head h3 {
  margin: 0 0 4px;
  font-size: 15px;
}
.cap-head p {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--muted, #8a8f9a);
}
.cap-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
}
.cap-item {
  border-top: 1px solid var(--line, #2c2f36);
  padding-top: 10px;
}
.cap-item:first-child {
  border-top: 0;
  padding-top: 0;
}
.cap-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.cap-tag {
  font-weight: 600;
  min-width: 84px;
}
.cap-levels {
  display: inline-flex;
  border: 1px solid var(--line, #2c2f36);
  border-radius: 8px;
  overflow: hidden;
}
.cap-level {
  border: 0;
  background: transparent;
  color: var(--muted, #8a8f9a);
  padding: 3px 8px;
  font-size: 12px;
  cursor: pointer;
}
.cap-level.active {
  background: var(--accent, #e8b04b);
  color: #15161a;
  font-weight: 600;
}
.cap-level.disabled {
  cursor: default;
}
.cap-status {
  margin-left: auto;
  font-size: 12px;
  color: var(--muted, #8a8f9a);
}
.cap-status.met {
  color: #5ec98a;
}
.cap-status.over {
  color: #7fb8ff;
}
.cap-acceptance {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--muted, #8a8f9a);
  line-height: 1.6;
}
.cap-empty {
  font-size: 12px;
  color: var(--muted, #8a8f9a);
}
</style>
