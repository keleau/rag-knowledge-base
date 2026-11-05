<script setup lang="ts">
import { computed } from 'vue'
import ReviewSheet from '../components/ReviewSheet.vue'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
}>()

const emit = defineEmits<{
  (event: 'repeat'): void
}>()

const report = computed(() => props.detail.report)
const projectName = computed(() => props.detail.selected_project?.name || props.detail.session.title)
const reviewDate = computed(() =>
  new Date(props.detail.session.updated_at).toLocaleDateString('zh-CN'),
)

function printReport() {
  window.print()
}
</script>

<template>
  <div v-if="!report" class="empty">
    <strong>还没有生成复盘。</strong>
    <p>完成面试后生成报告，这里会变成一张可打印的答辩复盘单。</p>
  </div>

  <div v-else class="report-page">
    <ReviewSheet
      :report="report"
      :project-name="projectName"
      :review-date="reviewDate"
      @repeat="emit('repeat')"
      @print="printReport"
    />
  </div>
</template>

<style scoped>
.report-page {
  width: min(920px, 100%);
  margin: 0 auto;
}

.empty {
  display: grid;
  gap: 6px;
  padding: 48px 0;
  color: var(--muted, #a6b0a7);
}

.empty strong {
  color: var(--ink-soft, #d7d0c2);
  font-size: 15px;
}

.empty p {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
}
</style>
