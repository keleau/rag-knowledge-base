<script setup lang="ts">
import { computed } from 'vue'
import SetupStep from './SetupStep.vue'
import type { AssessmentDetail } from '../types'

const props = defineProps<{
  detail: AssessmentDetail
}>()

const emit = defineEmits<{
  (event: 'enter-learning'): void
}>()

const ready = computed(
  () =>
    Boolean(props.detail.session.project_document_id) &&
    props.detail.tags.length > 0 &&
    props.detail.capabilities.length > 0 &&
    props.detail.practice.count > 0,
)
</script>

<template>
  <SetupStep :index="4" title="进入学习" entry>
    <template #description>
      <p v-if="ready">
        已生成 {{ detail.practice.count }} 道练习题（含代码题）、{{ detail.tags.length }} 个标签、{{ detail.capabilities.length }} 条能力目标。
      </p>
      <p v-else>完成上面三步后，可以开始 ≥20 道练习题。</p>
    </template>
    <button class="setup-primary" type="button" :disabled="!ready" @click="emit('enter-learning')">
      开始学习
    </button>
  </SetupStep>
</template>
