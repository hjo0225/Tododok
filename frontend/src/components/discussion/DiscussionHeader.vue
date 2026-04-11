<script setup lang="ts">
defineProps<{
  title: string
  round: number
  maxRounds: number
}>()
</script>

<template>
  <div
    class="flex-shrink-0"
    style="background: #fff; border-bottom: 1px solid #E5E8EB;"
  >
    <!-- 스텝 인디케이터 -->
    <div class="flex items-center justify-center gap-2 px-4 py-2 text-xs font-bold" style="border-bottom: 1px solid #E5E8EB;">
      <span style="color: #8B95A1;">① 읽기</span>
      <span style="color: #E5E8EB;">—</span>
      <span style="color: #8B95A1;">② 문제풀기</span>
      <span style="color: #E5E8EB;">—</span>
      <span style="color: #3182F6;">③ 토의</span>
      <span style="color: #E5E8EB;">—</span>
      <span style="color: #8B95A1;">④ 결과</span>
    </div>
    <!-- 제목 + 라운드 -->
    <div class="flex items-center justify-between px-4 py-2.5">
      <div class="flex items-center gap-2 min-w-0">
        <div class="w-2 h-2 rounded-full animate-pulse flex-shrink-0" style="background: #00C471;" />
        <span class="text-sm font-semibold truncate" style="color: #191F28;">{{ title }}</span>
      </div>
      <span
        class="text-xs px-3 py-1 rounded-full font-bold flex-shrink-0 ml-3"
        style="background: #FFF4E5; color: #FF9500;"
      >
        라운드 {{ round }} / {{ maxRounds }}
      </span>
    </div>
  </div>
</template>
