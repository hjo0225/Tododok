<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useStudentStore } from '@/stores/student'
import { useSessionStore } from '@/stores/session'
import apiClient from '@/api/client'

const router = useRouter()
const studentStore = useStudentStore()
const sessionStore = useSessionStore()

const todayCount = ref(0)
const loadingCount = ref(true)
const starting = ref(false)
const error = ref<string | null>(null)

const studentName = computed(() => studentStore.student?.name ?? '')
const streakCount = computed(() => studentStore.student?.streak_count ?? 0)
const limitReached = computed(() => todayCount.value >= 3)

onMounted(async () => {
  try {
    const meRes = await apiClient.get('/student/me')
    studentStore.updateStudent({
      name: meRes.data.name,
      level: meRes.data.level,
      streak_count: meRes.data.streak_count,
    })
    todayCount.value = meRes.data.today_session_count
  } catch {
    // 조회 실패 시 기존 로컬 상태 유지
  }

  try {
    const { data } = await apiClient.get('/student/sessions/today-count')
    todayCount.value = data.count
  } catch {
    // 조회 실패 시 0으로 유지
  } finally {
    loadingCount.value = false
  }
})

async function handleStart() {
  if (limitReached.value) return
  error.value = null
  starting.value = true
  try {
    const { data } = await apiClient.post('/student/sessions')
    sessionStore.startSession(data)
    router.push('/student/session')
  } catch (e: any) {
    if (e.response?.status === 429) {
      todayCount.value = 3
    } else {
      error.value = '학습을 시작할 수 없어요. 잠시 후 다시 시도해주세요.'
    }
  } finally {
    starting.value = false
  }
}

function handleLogout() {
  studentStore.logout()
  router.push('/student/join')
}
</script>

<template>
  <div class="min-h-screen" style="background: #F8FAFF;">
    <!-- 네비게이션 -->
    <nav class="flex items-center justify-between px-6 py-4 shadow-sm" style="background: white; border-bottom: 1px solid #EBF0FC;">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-white font-black" style="background: #1B438A;">
          리
        </div>
        <span class="font-black text-lg" style="color: #1B438A;">리터</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-sm font-medium" style="color: #5A7AB8;">{{ studentName }}</span>
        <button
          @click="handleLogout"
          class="text-sm px-3 py-1.5 rounded-lg transition-all"
          style="color: #5A7AB8; border: 1px solid #EBF0FC;"
        >
          나가기
        </button>
      </div>
    </nav>

    <!-- 메인 콘텐츠 -->
    <div class="max-w-sm mx-auto px-4 pt-10 flex flex-col gap-5">
      <!-- Streak 카드 -->
      <div class="rounded-2xl p-6 text-center" style="background: white; border: 1px solid #EBF0FC;">
        <div class="text-5xl mb-2">🔥</div>
        <div class="font-black text-4xl mb-1" style="color: #1B438A;">{{ streakCount }}일 연속</div>
        <p class="text-sm" style="color: #5A7AB8;">매일 꾸준히 하고 있어요!</p>
      </div>

      <!-- 오늘 세션 현황 -->
      <div class="rounded-2xl p-6" style="background: white; border: 1px solid #EBF0FC;">
        <div class="flex items-center justify-between mb-4">
          <span class="font-bold" style="color: #081830;">오늘의 학습</span>
          <span class="font-black text-lg" style="color: #1B438A;">{{ todayCount }}/3</span>
        </div>
        <!-- 진행 점 -->
        <div class="flex gap-2">
          <div
            v-for="i in 3"
            :key="i"
            class="flex-1 h-3 rounded-full transition-all"
            :style="{
              background: i <= todayCount ? '#1B438A' : '#EBF0FC',
            }"
          />
        </div>
      </div>

      <!-- 에러 -->
      <p v-if="error" class="text-sm text-center" style="color: #DC2626;">{{ error }}</p>

      <!-- 학습 시작 버튼 또는 완료 메시지 -->
      <div v-if="limitReached" class="rounded-2xl p-6 text-center" style="background: #EBF0FC;">
        <div class="text-3xl mb-2">👋</div>
        <p class="font-bold" style="color: #1B438A;">오늘은 여기까지!</p>
        <p class="text-sm mt-1" style="color: #5A7AB8;">내일 또 만나요</p>
      </div>

      <button
        v-else
        @click="handleStart"
        :disabled="starting || loadingCount"
        class="w-full py-4 rounded-2xl font-bold text-lg text-white transition-all"
        :style="{
          background: starting || loadingCount ? '#CBD5E1' : '#1B438A',
          cursor: starting || loadingCount ? 'not-allowed' : 'pointer',
        }"
      >
        {{ starting ? '불러오는 중...' : '학습 시작 →' }}
      </button>
    </div>
  </div>
</template>
