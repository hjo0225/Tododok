<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { useStudentStore } from '@/stores/student'
import apiClient from '@/api/client'
import { API_BASE_URL } from '@/api/config'
import DiscussionHeader from '@/components/discussion/DiscussionHeader.vue'
import DiscussionMessageList from '@/components/discussion/DiscussionMessageList.vue'
import DiscussionInput from '@/components/discussion/DiscussionInput.vue'
import { type DisplayMessage, type Speaker } from '@/components/discussion/types'

const MAX_ROUNDS = 10

const router = useRouter()
const sessionStore = useSessionStore()
const studentStore = useStudentStore()

const messages = ref<DisplayMessage[]>([])
const inputText = ref('')
const isLoading = ref(false)
const waitingForUser = ref(false)
const isDone = ref(false)
const discussionError = ref<string | null>(null)
const round = ref(1)
const messageListRef = ref<InstanceType<typeof DiscussionMessageList> | null>(null)

let msgIdCounter = 0
const nextId = () => ++msgIdCounter

onMounted(() => {
  if (!sessionStore.sessionId) {
    router.replace('/student/home')
    return
  }
  window.addEventListener('beforeunload', handleBeforeUnload)
  callDiscussion('')
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

function handleBeforeUnload() {
  void abandonSession(true)
}

async function callDiscussion(userContent: string) {
  if (!sessionStore.sessionId) return
  isLoading.value = true
  waitingForUser.value = false
  discussionError.value = null

  const token = studentStore.token

  try {
    const response = await fetch(`${API_BASE_URL}/student/sessions/${sessionStore.sessionId}/discussion`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content: userContent }),
    })

    if (!response.ok || !response.body) {
      isLoading.value = false
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue

        let event: Record<string, unknown>
        try { event = JSON.parse(raw) } catch { continue }

        if (event.speaker) {
          await new Promise<void>(res => setTimeout(res, 400 + Math.random() * 300))
          messages.value.push({
            id: nextId(),
            speaker: event.speaker as Speaker,
            content: event.content as string,
            round: event.round as number,
          })
          round.value = event.round as number
          await messageListRef.value?.scrollToBottom()
        } else if (event.next_speaker === 'user') {
          isLoading.value = false
          waitingForUser.value = true
          round.value = event.round as number
          await messageListRef.value?.scrollToBottom()
        } else if (event.error) {
          isLoading.value = false
          waitingForUser.value = false
          discussionError.value = '토의 응답을 생성하지 못했어요. 다시 시도해주세요.'
          await messageListRef.value?.scrollToBottom()
        } else if (event.is_final) {
          isLoading.value = false
          isDone.value = true
          await messageListRef.value?.scrollToBottom()
          setTimeout(() => endSession(), 1500)
        }
      }
    }
  } catch {
    isLoading.value = false
    discussionError.value = '토의 연결에 실패했어요. 다시 시도해주세요.'
  }
}

async function abandonSession(keepalive = false) {
  if (!sessionStore.sessionId || isDone.value) return
  const token = studentStore.token
  try {
    await fetch(`${API_BASE_URL}/student/sessions/${sessionStore.sessionId}`, {
      method: 'DELETE',
      keepalive,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
  } catch {
    // 페이지 이탈 중 요청 실패는 무시
  }
}

async function handleSend() {
  if (!inputText.value.trim() || !waitingForUser.value || isDone.value) return

  const content = inputText.value.trim()
  messages.value.push({
    id: nextId(),
    speaker: 'user',
    content,
    round: round.value,
  })
  sessionStore.addDiscussionMessage({ speaker: 'user', content, round: round.value })
  inputText.value = ''
  await messageListRef.value?.scrollToBottom()

  await callDiscussion(content)
}

async function endSession() {
  try {
    const res = await apiClient.post(`/student/sessions/${sessionStore.sessionId}/end`)
    studentStore.updateStudent({ streak_count: res.data.streak_count })
    sessionStore.setScores(res.data)
    router.push('/student/result')
  } catch {
    router.push('/student/home')
  }
}
</script>

<template>
  <div class="min-h-screen flex items-start justify-center" style="background: #F8FAFF;">
    <div class="w-full max-w-md min-h-screen flex flex-col" style="background: white;">

      <DiscussionHeader
        :title="sessionStore.passage?.title ?? 'AI 그룹 토의'"
        :round="round"
        :max-rounds="MAX_ROUNDS"
      />

      <DiscussionMessageList
        ref="messageListRef"
        :messages="messages"
        :is-loading="isLoading"
        :is-done="isDone"
        :error="discussionError"
      />

      <DiscussionInput
        v-model="inputText"
        :waiting-for-user="waitingForUser"
        :is-done="isDone"
        @send="handleSend"
      />

    </div>
  </div>
</template>
