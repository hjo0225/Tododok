<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { SPEAKERS, type DisplayMessage } from './types'

const props = defineProps<{
  messages: DisplayMessage[]
  isLoading: boolean
  isDone: boolean
  error: string | null
  studentName?: string
}>()

const chatRef = ref<HTMLDivElement | null>(null)

async function scrollToBottom() {
  await nextTick()
  chatRef.value?.scrollTo({ top: chatRef.value.scrollHeight, behavior: 'smooth' })
}

defineExpose({ scrollToBottom })
</script>

<template>
  <div
    ref="chatRef"
    class="flex-1 overflow-y-auto px-4 py-3 space-y-3"
    style="background: #081830; border-top: 1px solid #1B3A6B;"
  >
    <!-- 헤더 라벨 -->
    <div class="sticky top-0 pb-2" style="background: #081830;">
      <span class="text-xs font-semibold" style="color: #5A7AB8;">대화 기록</span>
    </div>

    <template v-for="msg in messages" :key="msg.id">
      <div class="flex items-start gap-2">
        <!-- 아바타 -->
        <div
          class="w-6 h-6 rounded-full flex items-center justify-center text-white flex-shrink-0 mt-0.5"
          :style="{ background: SPEAKERS[msg.speaker].color, fontSize: '9px', fontWeight: '800' }"
        >
          {{ SPEAKERS[msg.speaker].emoji }}
        </div>

        <!-- 내용 -->
        <div class="min-w-0">
          <span class="text-xs font-bold mr-2" :style="{ color: SPEAKERS[msg.speaker].color }">
            {{ msg.speaker === 'user' && props.studentName ? props.studentName : SPEAKERS[msg.speaker].name }}
          </span>
          <p class="text-sm leading-relaxed" style="color: #d1d5db;">{{ msg.content }}</p>
        </div>
      </div>
    </template>

    <!-- 로딩 점 -->
    <div v-if="isLoading" class="flex items-center gap-2 pl-8">
      <span
        v-for="i in 3"
        :key="i"
        class="w-2 h-2 rounded-full animate-bounce"
        :style="{ background: '#2653AC', animationDelay: `${(i - 1) * 0.15}s` }"
      />
    </div>

    <!-- 토의 완료 -->
    <div v-if="isDone" class="text-center py-4">
      <div class="text-2xl mb-1">🎉</div>
      <p class="text-sm font-bold" style="color: #60a5fa;">토의 완료! 결과를 확인해요...</p>
    </div>

    <p v-if="error" class="text-sm text-center font-semibold" style="color: #f87171;">
      {{ error }}
    </p>
  </div>
</template>
