<script setup lang="ts">
import type { ConfirmRequiredPayload } from '../types'

defineProps<{ request: ConfirmRequiredPayload }>()
const emit = defineEmits<{ decide: [approved: boolean] }>()
</script>

<template>
  <div class="confirm-card" data-testid="confirm-card">
    <p class="confirm-card__title">这一步会真的执行 <code>{{ request.tool }}</code>，需要你确认</p>
    <pre class="confirm-card__args">{{ JSON.stringify(request.args, null, 2) }}</pre>
    <div class="confirm-card__actions">
      <button type="button" class="confirm-card__approve" data-testid="confirm-approve" @click="emit('decide', true)">
        批准执行
      </button>
      <button type="button" class="confirm-card__reject" data-testid="confirm-reject" @click="emit('decide', false)">
        拒绝
      </button>
    </div>
  </div>
</template>

<style scoped>
.confirm-card {
  border: 1px solid #f0c36d;
  background: #fff8e6;
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.confirm-card__title {
  margin: 0;
  font-size: 14px;
  color: #6b5100;
}
.confirm-card__args {
  margin: 0;
  background: #fffdf5;
  border: 1px solid #f0e0b0;
  border-radius: 6px;
  padding: 8px;
  font-size: 12px;
  overflow-x: auto;
}
.confirm-card__actions {
  display: flex;
  gap: 8px;
}
.confirm-card__approve,
.confirm-card__reject {
  border-radius: 6px;
  padding: 6px 14px;
  cursor: pointer;
  border: 1px solid transparent;
}
.confirm-card__approve {
  background: #2f7d3c;
  color: white;
}
.confirm-card__reject {
  background: white;
  border-color: #c94b4b;
  color: #c94b4b;
}
</style>
