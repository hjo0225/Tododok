<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { SPEAKERS, type DisplayMessage } from './types'

defineProps<{
  messages: DisplayMessage[]
  isLoading: boolean
  isDone: boolean
  error: string | null
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
    class="flex-1 overflow-y-auto flex flex-col gap-4 px-4 py-4"
    style="background: #F8FAFF;"
  >
    <template v-for="msg in messages" :key="msg.id">
      <div
        class="flex flex-col gap-1"
        :class="msg.speaker === 'user' ? 'items-end' : 'items-start'"
      >
        <!-- 발화자 이름 (user 제외) -->
        <div v-if="msg.speaker !== 'user'" class="flex items-center gap-1.5 ml-2">
          <div
            class="w-5 h-5 rounded-full flex items-center justify-center text-white"
            :style="{ background: SPEAKERS[msg.speaker].color, fontSize: '9px', fontWeight: '800' }"
          >
            {{ SPEAKERS[msg.speaker].emoji }}
          </div>
          <span class="text-xs" style="color: #93B2E8; font-weight: 500;">
            {{ SPEAKERS[msg.speaker].name }}
          </span>
        </div>

        <!-- 말풍선 -->
        <div
          class="px-4 py-3 text-sm leading-relaxed"
          :style="{
            background: msg.speaker === 'user' ? '#1B438A' : 'white',
            color: msg.speaker === 'user' ? 'white' : '#081830',
            border: msg.speaker === 'user' ? 'none' : '1px solid #EBF0FC',
            borderRadius: msg.speaker === 'user' ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
            alignSelf: msg.speaker === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '78%',
          }"
        >
          {{ msg.content }}
        </div>
      </div>
    </template>

    <!-- 로딩 점 -->
    <div v-if="isLoading" class="flex items-center gap-2">
      <div
        class="flex gap-1.5 px-4 py-3 rounded-2xl"
        style="background: white; border: 1px solid #EBF0FC;"
      >
        <span
          v-for="i in 3"
          :key="i"
          class="w-2 h-2 rounded-full animate-bounce"
          :style="{ background: '#C0D0F6', animationDelay: `${(i - 1) * 0.15}s` }"
        />
      </div>
    </div>

    <!-- 토의 완료 -->
    <div v-if="isDone" class="text-center py-4">
      <div class="text-3xl mb-2">🎉</div>
      <p class="text-sm font-bold" style="color: #1B438A;">
        토의가 완료됐어요! 결과를 확인해요...
      </p>
    </div>

    <p v-if="error" class="text-sm text-center font-semibold" style="color: #DC2626;">
      {{ error }}
    </p>
  </div>
</template>
