<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../markdown'
import type { TimelineEntry } from '../types'

const props = defineProps<{ entry: TimelineEntry }>()

const renderedHtml = computed(() => {
  if (props.entry.kind === 'assistant') return renderMarkdown(props.entry.content)
  return ''
})
</script>

<template>
  <div class="timeline-item" :class="`timeline-item--${entry.kind}`">
    <div v-if="entry.kind === 'user'" class="bubble bubble--user">{{ entry.content }}</div>

    <div v-else-if="entry.kind === 'assistant'" class="bubble bubble--assistant markdown-body" v-html="renderedHtml" />

    <div v-else-if="entry.kind === 'tool_call'" class="tool-indicator" data-testid="tool-call">
      🔧 正在调用工具 <code>{{ entry.tool }}</code>…
    </div>

    <div
      v-else-if="entry.kind === 'tool_result'"
      class="tool-indicator"
      :class="entry.ok ? 'tool-indicator--ok' : 'tool-indicator--error'"
      data-testid="tool-result"
    >
      {{ entry.ok ? '✅' : '⚠️' }} <code>{{ entry.tool }}</code>：{{ entry.summary }}
    </div>
  </div>
</template>

<style scoped>
.timeline-item {
  display: flex;
  margin: 6px 0;
}
.timeline-item--user {
  justify-content: flex-end;
}
.timeline-item--assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 10px;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble--user {
  background: #2f6fed;
  color: white;
}
.bubble--assistant {
  background: #f0f1f3;
  color: #1a1a1a;
}
.tool-indicator {
  font-size: 13px;
  color: #666;
  background: #f7f7f8;
  border-radius: 8px;
  padding: 6px 10px;
}
.tool-indicator--ok {
  color: #1e7a34;
}
.tool-indicator--error {
  color: #b3261e;
}
.markdown-body :deep(pre) {
  background: #1e1e1e;
  color: #ddd;
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
}
.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
