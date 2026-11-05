<script setup lang="ts">
import { computed } from 'vue'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
}>()

const items = computed(() => props.detail.entities.slice(0, 40))
const codeFiles = computed(() => (props.detail.code ? [props.detail.code.file_name] : []))
</script>

<template>
  <details class="entity-debug">
    <summary>
      出题依据 · {{ detail.entities.length }} 个项目实体
      <span v-if="codeFiles.length" class="debug-code">· 代码 {{ codeFiles[0] }}</span>
    </summary>
    <div class="entity-groups">
      <span v-for="entity in items" :key="entity.id" class="entity-chip" :class="entity.source_type">
        {{ entity.name }}
        <em>{{ entity.kind }}</em>
      </span>
      <p v-if="!items.length" class="debug-empty">还没有抽取到实体，请先上传项目文档。</p>
    </div>
    <p class="debug-note">
      题干里没有这些词的题会被直接丢弃；考试题还会与练习题做跨阶段去重。
    </p>
  </details>
</template>

<style scoped>
.entity-debug {
  border: 1px dashed var(--line, #2c2f36);
  border-radius: 12px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.015);
}
.entity-debug summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--muted, #8a8f9a);
}
.debug-code {
  color: #7fb8ff;
}
.entity-groups {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0;
}
.entity-chip {
  font-size: 12px;
  border: 1px solid var(--line, #2c2f36);
  border-radius: 999px;
  padding: 2px 9px;
  font-family: monospace;
}
.entity-chip.code {
  border-color: rgba(127, 184, 255, 0.5);
  color: #7fb8ff;
}
.entity-chip em {
  font-style: normal;
  color: #6b707c;
  margin-left: 4px;
}
.debug-empty,
.debug-note {
  font-size: 12px;
  color: var(--muted, #8a8f9a);
  margin: 6px 0 0;
}
</style>
