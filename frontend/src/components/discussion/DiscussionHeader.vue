<script setup lang="ts">
import { SPEAKERS } from './types'

defineProps<{
  title: string
  round: number
  maxRounds: number
}>()
</script>

<template>
  <div style="border-bottom: 1px solid #EBF0FC;">
    <div class="flex items-center justify-between px-4 py-3">
      <span class="text-sm font-bold truncate pr-2" style="color: #112B5C; max-width: 200px;">
        {{ title }}
      </span>
      <span
        class="text-xs px-2.5 py-1 rounded-full shrink-0 font-bold"
        style="background: #EBF0FC; color: #1B438A;"
      >
        {{ round }} / {{ maxRounds }}라운드
      </span>
    </div>

    <!-- 참여자 -->
    <div class="flex gap-2 px-4 pb-3 flex-wrap">
      <div
        v-for="(s, key) in SPEAKERS"
        :key="key"
        class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
        :style="{ background: s.bg, color: s.textColor }"
      >
        <div
          class="w-4 h-4 rounded-full flex items-center justify-center text-white"
          :style="{ background: s.color, fontSize: '9px', fontWeight: '800' }"
        >
          {{ s.emoji }}
        </div>
        {{ s.name }}
      </div>
    </div>

    <!-- 진행 바 -->
    <div style="height: 3px; background: #EBF0FC;">
      <div
        :style="{ width: `${(round / maxRounds) * 100}%`, height: '100%', background: '#1B438A', borderRadius: '2px', transition: 'width 0.3s' }"
      />
    </div>
    <div class="text-right px-4 py-1">
      <span class="text-xs" style="color: #93B2E8;">3 / 3단계 — AI 그룹 토의</span>
    </div>
  </div>
</template>
