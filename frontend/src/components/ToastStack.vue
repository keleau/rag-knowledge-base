<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { Toast } from '../types'

defineProps<{ toasts: Toast[] }>()

const emit = defineEmits<{
  (event: 'dismiss', id: number): void
}>()
</script>

<template>
  <Teleport to="body">
    <TransitionGroup name="toast" tag="div" class="toast-stack" aria-live="polite">
      <div v-for="toast in toasts" :key="toast.id" class="toast" :class="toast.kind" role="status">
        <span class="toast-icon">
          <AppIcon :name="toast.kind === 'success' ? 'check' : toast.kind === 'error' ? 'alert' : 'info'" :size="16" />
        </span>
        <span class="toast-message">{{ toast.message }}</span>
        <button class="toast-close" aria-label="关闭提示" @click="emit('dismiss', toast.id)">
          <AppIcon name="close" :size="14" />
        </button>
      </div>
    </TransitionGroup>
  </Teleport>
</template>
