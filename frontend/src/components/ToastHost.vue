<script setup>
defineProps({
  toasts: { type: Array, default: () => [] },
})
const emit = defineEmits(['dismiss'])
</script>

<template>
  <div class="toast-host">
    <TransitionGroup name="toast">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast"
        :class="t.type"
        @click="emit('dismiss', t.id)"
      >
        {{ t.message }}
      </div>
    </TransitionGroup>
  </div>
</template>
