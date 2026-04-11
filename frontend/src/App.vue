<template>
  <RouterView v-slot="{ Component }">
    <Transition :name="transitionName" mode="out-in">
      <component :is="Component" :key="$route.path" />
    </Transition>
  </RouterView>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const transitionName = ref('slide-left')

watch(
  () => route.meta.order,
  (newOrder, oldOrder) => {
    const n = (newOrder as number) ?? 0
    const o = (oldOrder as number) ?? 0
    transitionName.value = n >= o ? 'slide-left' : 'slide-right'
  },
)
</script>

<style>
/* ── Slide Left (앞으로 진행) ── */
.slide-left-enter-active,
.slide-left-leave-active {
  transition: opacity 0.28s ease, transform 0.28s ease;
}
.slide-left-enter-from {
  opacity: 0;
  transform: translateX(40px);
}
.slide-left-leave-to {
  opacity: 0;
  transform: translateX(-40px);
}

/* ── Slide Right (뒤로 이동) ── */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: opacity 0.28s ease, transform 0.28s ease;
}
.slide-right-enter-from {
  opacity: 0;
  transform: translateX(-40px);
}
.slide-right-leave-to {
  opacity: 0;
  transform: translateX(40px);
}
</style>
