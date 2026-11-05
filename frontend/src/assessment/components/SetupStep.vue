<script setup lang="ts">
defineProps<{
  index: number | string
  title: string
  description?: string
  locked?: boolean
  entry?: boolean
}>()
</script>

<template>
  <section class="setup-step" :class="{ locked, entry }">
    <header class="setup-step-head">
      <span class="setup-index">{{ index }}</span>
      <div>
        <h2>{{ title }}</h2>
        <slot name="description">
          <p v-if="description">{{ description }}</p>
        </slot>
      </div>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.setup-step {
  padding: 18px 20px;
  border: 1px solid var(--line, #2c3a32);
  border-radius: 16px;
  background: var(--panel, #171d19);
}

.setup-step.locked {
  opacity: 0.78;
}

.setup-step.entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.setup-step.entry .setup-step-head {
  flex: 1;
  margin-bottom: 0;
}

.setup-step-head {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}

.setup-index {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: rgba(215, 166, 79, 0.16);
  color: var(--amber, #d7a64f);
  font-weight: 700;
}

.setup-step-head h2 {
  margin: 0 0 4px;
  font-size: 16px;
}

.setup-step-head p {
  margin: 0;
  color: var(--muted, #a6b0a7);
  font-size: 12.5px;
  line-height: 1.55;
}

.setup-step-head code {
  font-size: 12px;
}

@media (max-width: 620px) {
  .setup-step {
    padding: 16px;
  }

  .setup-step.entry {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
