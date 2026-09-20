<script setup lang="ts">
import type { DisplayError } from '../types'

defineProps<{ error: DisplayError }>()
const emit = defineEmits<{ retry: []; dismiss: [] }>()
</script>

<template>
  <div class="error-banner" role="alert">
    <div class="error-banner__text">
      <strong>{{ error.title }}</strong>
      <span>{{ error.message }}</span>
    </div>
    <div class="error-banner__actions">
      <button v-if="error.retryable" type="button" class="error-banner__retry" @click="emit('retry')">
        重试
      </button>
      <button type="button" class="error-banner__dismiss" @click="emit('dismiss')" aria-label="关闭">
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: #fdecea;
  border: 1px solid #f5c2c0;
  color: #7a1f1a;
}
.error-banner__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 14px;
}
.error-banner__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.error-banner__retry {
  border: 1px solid #d9534f;
  background: white;
  color: #d9534f;
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
}
.error-banner__dismiss {
  border: none;
  background: transparent;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  color: inherit;
}
</style>
