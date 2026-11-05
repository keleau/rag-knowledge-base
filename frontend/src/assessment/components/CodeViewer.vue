<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  content: string
  start?: number | null
  end?: number | null
  file?: string | null
  fileLine?: string[] | null
}>()

const lines = computed(() => {
  const raw = (props.content || '').replace(/\r\n/g, '\n').split('\n')
  const start = props.start || 1
  const end = props.end || raw.length
  return raw
    .slice(Math.max(0, start - 1), Math.max(start, end))
    .map((text, offset) => ({ number: start + offset, text }))
})
</script>

<template>
  <figure class="code-viewer">
    <figcaption v-if="file">{{ file }}<span v-if="start"> · 第 {{ start }}–{{ end }} 行</span></figcaption>
    <ol class="code-lines">
      <li
        v-for="line in lines"
        :key="line.number"
        :class="{ highlighted: fileLine?.includes(line.text.trim()) }"
      >
        <span class="code-no">{{ line.number }}</span>
        <span class="code-text">{{ line.text || ' ' }}</span>
      </li>
    </ol>
  </figure>
</template>

<style scoped>
.code-viewer {
  margin: 10px 0 0;
  border: 1px solid var(--line, #2c2f36);
  border-radius: 10px;
  overflow: hidden;
  background: #101116;
}
.code-viewer figcaption {
  padding: 6px 12px;
  font-size: 12px;
  color: var(--muted, #8a8f9a);
  background: #15161c;
  border-bottom: 1px solid var(--line, #2c2f36);
}
.code-lines {
  list-style: none;
  margin: 0;
  padding: 8px 0;
  max-height: 320px;
  overflow: auto;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
.code-lines li {
  display: flex;
  gap: 12px;
  padding: 0 12px;
  white-space: pre;
}
.code-lines li.highlighted {
  background: rgba(232, 176, 75, 0.12);
}
.code-no {
  color: #555b68;
  min-width: 3ch;
  text-align: right;
  user-select: none;
}
.code-text {
  color: #d6d9e0;
}
</style>
