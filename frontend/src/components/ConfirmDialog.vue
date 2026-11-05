<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    message: string
    confirmLabel?: string
    danger?: boolean
  }>(),
  { confirmLabel: '确认', danger: false },
)

const emit = defineEmits<{
  (event: 'confirm'): void
  (event: 'cancel'): void
}>()

const cancelButton = ref<HTMLButtonElement | null>(null)

function onKeydown(event: KeyboardEvent) {
  if (props.open && event.key === 'Escape') emit('cancel')
}

watch(
  () => props.open,
  (open) => {
    if (open) nextTick(() => cancelButton.value?.focus())
  },
)

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" @click.self="emit('cancel')">
        <div
          class="confirm-dialog"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="confirm-title"
          aria-describedby="confirm-message"
        >
          <span class="confirm-icon" :class="{ danger }">
            <AppIcon :name="danger ? 'alert' : 'info'" :size="20" />
          </span>
          <h2 id="confirm-title">{{ title }}</h2>
          <p id="confirm-message">{{ message }}</p>
          <div class="confirm-actions">
            <button ref="cancelButton" class="ghost-btn" @click="emit('cancel')">取消</button>
            <button class="primary-btn" :class="{ danger }" @click="emit('confirm')">
              {{ confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
