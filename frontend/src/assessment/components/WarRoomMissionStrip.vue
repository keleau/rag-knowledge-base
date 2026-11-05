<script setup lang="ts">
import { MISSION_STAGES, type MissionKey } from '../mission'

defineProps<{
  groupIndex: number
}>()

const emit = defineEmits<{
  (event: 'select', key: MissionKey): void
}>()
</script>

<template>
  <nav class="mission-strip" aria-label="训练阶段">
    <button
      v-for="(item, index) in MISSION_STAGES"
      :key="item.key"
      class="mission-step"
      :class="{ active: index === groupIndex, done: index < groupIndex, locked: index > groupIndex }"
      :disabled="index > groupIndex"
      type="button"
      @click="emit('select', item.key)"
    >
      <em>{{ String(index + 1).padStart(2, '0') }}</em>
      <span>{{ item.label }}</span>
      <small v-if="index < groupIndex">已过</small>
      <small v-else-if="index === groupIndex">当前</small>
      <small v-else-if="index === groupIndex + 1">待开始</small>
      <small v-else>未解锁</small>
    </button>
  </nav>
</template>

<style scoped>
.mission-strip {
  flex: none;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  background: var(--surface, #151b17);
  border-bottom: 1px solid var(--line, #2c3a32);
}

.mission-step {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 8px;
  border-bottom: 2px solid transparent;
  color: rgba(245, 242, 234, 0.58);
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.mission-step em {
  font-family: var(--font-mono, monospace);
  font-style: normal;
  font-size: 10px;
  opacity: 0.7;
}

.mission-step span {
  font-size: 13px;
}

.mission-step small {
  font-size: 10px;
  color: rgba(245, 242, 234, 0.42);
}

.mission-step:not(:disabled):hover {
  background: rgba(245, 242, 234, 0.04);
  color: var(--ink-soft, #d7d0c2);
}

.mission-step.active {
  color: var(--cream, #f2eee3);
  border-bottom-color: var(--amber, #d7a64f);
}

.mission-step.active em {
  color: var(--amber, #d7a64f);
  opacity: 1;
}

.mission-step.done {
  color: rgba(245, 242, 234, 0.78);
}

.mission-step.done small {
  color: #8fc9a9;
}

.mission-step.active small {
  color: var(--amber, #d7a64f);
}

.mission-step.locked {
  opacity: 0.38;
}

@media (prefers-reduced-motion: reduce) {
  .mission-step {
    transition: none;
  }
}

@media (max-width: 900px) {
  .mission-step {
    flex-direction: column;
    gap: 2px;
    padding: 8px 2px;
    text-align: center;
  }

  .mission-step small {
    display: none;
  }
}
</style>
