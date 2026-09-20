<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { useChat } from '../composables/useChat'
import * as conversationsApi from '../api/conversations'
import { ApiError } from '../api/client'
import ErrorBanner from '../components/ErrorBanner.vue'
import ConfirmCard from '../components/ConfirmCard.vue'
import TimelineItem from '../components/TimelineItem.vue'
import type { Conversation } from '../types'

const router = useRouter()
const { token, logout } = useAuth()

const conversations = ref<Conversation[]>([])
const activeConversationId = ref<number | null>(null)
const draft = ref('')
const loadError = ref<string | null>(null)

const chat = useChat(activeConversationId)

async function loadConversations() {
  if (!token.value) return
  try {
    conversations.value = await conversationsApi.listConversations(token.value)
    if (conversations.value.length > 0 && activeConversationId.value == null) {
      activeConversationId.value = conversations.value[0].id
    }
  } catch (e) {
    if (e instanceof ApiError && e.tier === 'auth') return handleAuthError()
    loadError.value = e instanceof Error ? e.message : String(e)
  }
}

async function newConversation() {
  if (!token.value) return
  const conv = await conversationsApi.createConversation(token.value, `对话 ${conversations.value.length + 1}`)
  conversations.value.unshift(conv)
  selectConversation(conv.id)
}

function selectConversation(id: number) {
  activeConversationId.value = id
  chat.reset()
}

function handleAuthError() {
  logout()
  router.push('/login')
}

async function send() {
  const text = draft.value
  draft.value = ''
  await chat.sendMessage(text)
}

onMounted(() => {
  if (!token.value) {
    router.push('/login')
    return
  }
  loadConversations()
})
</script>

<template>
  <div class="chat-page">
    <aside class="sidebar">
      <button type="button" class="sidebar__new" data-testid="new-conversation" @click="newConversation">
        + 新建对话
      </button>
      <ul class="sidebar__list">
        <li
          v-for="conv in conversations"
          :key="conv.id"
          :class="{ active: conv.id === activeConversationId }"
          @click="selectConversation(conv.id)"
        >
          {{ conv.title }}
        </li>
      </ul>
      <button type="button" class="sidebar__logout" @click="handleAuthError">退出登录</button>
    </aside>

    <main class="chat-main">
      <div v-if="loadError" class="chat-main__load-error">{{ loadError }}</div>

      <div v-if="!activeConversationId" class="chat-main__empty">
        点击左侧"新建对话"开始，或者选一个已有的会话。
      </div>

      <template v-else>
        <div class="timeline" data-testid="timeline">
          <TimelineItem v-for="entry in chat.timeline.value" :key="entry.id" :entry="entry" />
        </div>

        <ConfirmCard
          v-if="chat.pendingConfirmation.value"
          :request="chat.pendingConfirmation.value"
          @decide="chat.confirmPending"
        />

        <ErrorBanner
          v-if="chat.error.value"
          :error="chat.error.value"
          @retry="chat.retry"
          @dismiss="chat.error.value = null"
        />

        <form class="composer" @submit.prevent="send">
          <input
            v-model="draft"
            type="text"
            placeholder="跟 Agent 说点什么…"
            :disabled="chat.isStreaming.value || !!chat.pendingConfirmation.value"
            data-testid="message-input"
          />
          <button
            type="submit"
            :disabled="chat.isStreaming.value || !!chat.pendingConfirmation.value || !draft.trim()"
            data-testid="send-button"
          >
            {{ chat.isStreaming.value ? '发送中…' : '发送' }}
          </button>
        </form>
      </template>
    </main>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  height: 100vh;
  background: #f5f6fa;
}
.sidebar {
  width: 220px;
  background: #1f2430;
  color: white;
  display: flex;
  flex-direction: column;
  padding: 12px;
  gap: 8px;
}
.sidebar__new {
  padding: 8px;
  border-radius: 6px;
  border: 1px dashed #4a5064;
  background: transparent;
  color: white;
  cursor: pointer;
}
.sidebar__list {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  overflow-y: auto;
}
.sidebar__list li {
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.sidebar__list li.active,
.sidebar__list li:hover {
  background: #313850;
}
.sidebar__logout {
  border: none;
  background: transparent;
  color: #aaa;
  font-size: 12px;
  cursor: pointer;
}
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 24px;
  gap: 10px;
  max-width: 800px;
}
.chat-main__empty,
.chat-main__load-error {
  color: #888;
  margin-top: 40px;
  text-align: center;
}
.timeline {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.composer {
  display: flex;
  gap: 8px;
}
.composer input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
}
.composer button {
  padding: 0 18px;
  border: none;
  border-radius: 8px;
  background: #2f6fed;
  color: white;
  cursor: pointer;
}
.composer button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
