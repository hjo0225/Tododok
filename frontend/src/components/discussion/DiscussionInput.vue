<script setup lang="ts">
defineProps<{
  modelValue: string
  waitingForUser: boolean
  isDone: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
}>()

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send')
  }
}
</script>

<template>
  <div class="px-4 py-4 border-t" style="border-color: #EBF0FC; background: white;">
    <p
      v-if="waitingForUser && !isDone"
      class="text-xs text-center mb-2 font-semibold"
      style="color: #2653AC;"
    >
      💬 지금 내 의견을 말할 차례예요!
    </p>
    <div class="flex gap-2">
      <input
        :value="modelValue"
        type="text"
        :placeholder="waitingForUser && !isDone ? '내 의견을 입력해요...' : '상대방의 발언을 기다리는 중...'"
        :disabled="!waitingForUser || isDone"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        @keydown="handleKeydown"
        class="flex-1 px-4 py-3 rounded-2xl outline-none text-sm transition-all"
        :style="{
          border: `1.5px solid ${waitingForUser && !isDone ? '#1B438A' : '#EBF0FC'}`,
          background: waitingForUser && !isDone ? '#F8FAFF' : '#F0F4FD',
          color: '#081830',
        }"
      />
      <button
        @click="emit('send')"
        :disabled="!waitingForUser || !modelValue.trim() || isDone"
        class="w-11 h-11 rounded-full flex items-center justify-center shrink-0 transition-all"
        :style="{
          background: waitingForUser && modelValue.trim() && !isDone ? '#1B438A' : '#C0D0F6',
        }"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"/>
          <polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      </button>
    </div>
  </div>
</template>
