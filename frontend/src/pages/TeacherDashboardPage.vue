<template>
  <div class="min-h-screen" style="background-color: #F8FAFF">
    <!-- Top Nav -->
    <nav class="sticky top-0 z-40 border-b" style="background-color: white; border-color: #EBF0FC">
      <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <button
            @click="router.push('/teacher/classrooms')"
            class="flex items-center gap-1 text-sm"
            style="color: #5A7AB8"
          >
            <ChevronLeft :size="18" />
            학급 목록
          </button>
          <div class="h-5 w-px" style="background-color: #EBF0FC" />
          <div class="flex items-center gap-2">
            <div class="w-7 h-7 rounded-lg flex items-center justify-center" style="background-color: #1B438A">
              <span class="text-xs">📖</span>
            </div>
            <span style="font-weight: 800; color: #1B438A; font-size: 15px; letter-spacing: -0.3px">리터</span>
          </div>
        </div>
        <div v-if="dashboard" class="text-right">
          <div class="text-sm" style="color: #112B5C; font-weight: 700">{{ dashboard.classroom_name }}</div>
        </div>
      </div>
    </nav>

    <div v-if="loading" class="flex items-center justify-center h-64">
      <div class="text-sm" style="color: #93B2E8">불러오는 중...</div>
    </div>

    <div v-else-if="dashboard" class="max-w-7xl mx-auto px-6 py-8">
      <!-- Header -->
      <div class="mb-8">
        <h1 style="color: #081830; font-size: 1.5rem; font-weight: 800">{{ dashboard.classroom_name }} 대시보드 📊</h1>
        <p class="text-sm mt-1" style="color: #5A7AB8">학생들의 문해력 수준 변화와 취약 영역을 한눈에 확인해요</p>
      </div>

      <!-- Alert Banner -->
      <div
        v-if="attentionCount > 0"
        class="flex items-center gap-3 p-4 rounded-2xl mb-6"
        style="background-color: #FEF2F2; border: 1.5px solid #FECACA"
      >
        <AlertTriangle :size="18" color="#DC2626" />
        <div class="flex-1">
          <span class="text-sm" style="color: #991B1B; font-weight: 700">즉시 확인이 필요한 학생 {{ attentionCount }}명</span>
          <span class="text-xs ml-2" style="color: #B91C1C">(최근 3세션 평균 5점 이하)</span>
        </div>
        <button
          @click="activeFilter = 'attention'"
          class="text-xs px-3 py-1.5 rounded-lg"
          style="background-color: #DC2626; color: white; font-weight: 700"
        >
          확인하기
        </button>
      </div>

      <!-- Stats Grid -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div
          v-for="stat in statsGrid"
          :key="stat.label"
          class="rounded-2xl p-5"
          style="background-color: white; border: 1px solid #EBF0FC"
        >
          <div class="text-2xl mb-3">{{ stat.emoji }}</div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl" style="font-weight: 900; color: #1B438A">{{ stat.value }}</span>
            <span class="text-sm" style="color: #5A7AB8">{{ stat.unit }}</span>
          </div>
          <div class="text-xs mt-1" style="color: #93B2E8">{{ stat.sub || stat.label }}</div>
        </div>
      </div>

      <!-- Level Distribution -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
        <div
          v-for="level in ([3, 2, 1] as Array<1|2|3>)"
          :key="level"
          class="rounded-2xl p-5"
          style="background-color: white; border: 1px solid #EBF0FC"
        >
          <div class="flex items-center justify-between mb-3">
            <span
              class="px-3 py-1 rounded-lg text-sm"
              :style="{ backgroundColor: levelColors[level].bg, color: levelColors[level].text, fontWeight: 700 }"
            >
              {{ levelLabels[level] }}급
            </span>
            <span class="text-sm" style="color: #5A7AB8; font-weight: 500">
              {{ levelCount(level) }}명 ({{ levelPct(level) }}%)
            </span>
          </div>
          <div class="h-2 rounded-full" style="background-color: #EBF0FC">
            <div
              class="h-full rounded-full transition-all duration-700"
              :style="{ width: levelPct(level) + '%', backgroundColor: levelColors[level].text }"
            />
          </div>
        </div>
      </div>

      <!-- Filter Tabs -->
      <div class="flex gap-2 mb-4 flex-wrap">
        <button
          v-for="f in filterTabs"
          :key="f.key"
          @click="activeFilter = f.key"
          class="px-4 py-2 rounded-xl text-sm transition-all"
          :style="{
            backgroundColor: activeFilter === f.key ? '#1B438A' : 'white',
            color: activeFilter === f.key ? 'white' : '#5A7AB8',
            border: '1px solid #EBF0FC',
            fontWeight: activeFilter === f.key ? 700 : 500,
          }"
        >
          {{ f.label }}
        </button>
      </div>

      <!-- Student Table -->
      <div class="rounded-2xl overflow-hidden" style="background-color: white; border: 1px solid #EBF0FC">
        <!-- Table Header -->
        <div
          class="hidden md:grid gap-4 px-5 py-3"
          style="grid-template-columns: 2fr 1fr 2fr 1fr 1fr 80px 36px; background-color: #F8FAFF; border-bottom: 1px solid #EBF0FC"
        >
          <span
            v-for="h in ['학생', '수준', '취약 영역', 'streak', '평균 점수', '4주 추이', '']"
            :key="h"
            class="text-xs"
            style="color: #93B2E8; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase"
          >
            {{ h }}
          </span>
        </div>

        <!-- Rows -->
        <div>
          <div
            v-for="student in filteredStudents"
            :key="student.id"
            class="flex flex-col md:grid gap-4 px-5 py-4 items-start md:items-center border-b cursor-pointer hover:bg-slate-50 transition-colors"
            style="grid-template-columns: 2fr 1fr 2fr 1fr 1fr 80px 36px; border-color: #F0F4FD"
            :style="{ backgroundColor: student.needs_attention ? '#FFF5F5' : '' }"
            @click="openModal(student)"
          >
            <!-- Name -->
            <div class="flex items-center gap-2">
              <AlertTriangle v-if="student.needs_attention" :size="14" color="#DC2626" />
              <div
                class="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs flex-shrink-0"
                style="background-color: #2653AC; font-weight: 700"
              >
                {{ student.name[0] }}
              </div>
              <span class="text-sm" style="color: #112B5C; font-weight: 600">{{ student.name }}</span>
            </div>

            <!-- Level -->
            <div @click.stop>
              <button
                @click="toggleLevelEdit(student.id)"
                class="px-2.5 py-1 rounded-lg text-xs"
                :style="{ backgroundColor: levelColors[(student.level as 1|2|3)].bg, color: levelColors[(student.level as 1|2|3)].text, fontWeight: 700 }"
              >
                {{ student.teacher_override_level ? '✏️ ' : '' }}{{ levelLabels[(student.level as 1|2|3)] }}급
              </button>
              <div v-if="editingLevelId === student.id" class="flex gap-1 mt-1">
                <button
                  v-for="l in ([1, 2, 3] as Array<1|2|3>)"
                  :key="l"
                  @click="setLevel(student, l)"
                  class="px-2 py-1 rounded text-xs"
                  :style="{ backgroundColor: levelColors[l].bg, color: levelColors[l].text, fontWeight: 700 }"
                >
                  {{ levelLabels[l] }}
                </button>
              </div>
            </div>

            <!-- Weak Areas -->
            <div class="flex flex-wrap gap-1">
              <template v-if="student.weak_areas.length > 0">
                <span
                  v-for="tag in student.weak_areas.slice(0, 2)"
                  :key="tag"
                  class="px-2 py-0.5 rounded text-xs"
                  style="background-color: #EBF0FC; color: #2653AC; font-weight: 500"
                >
                  {{ tag }}
                </span>
              </template>
              <span v-else class="text-xs" style="color: #16A34A; font-weight: 500">✅ 양호</span>
            </div>

            <!-- Streak -->
            <div class="flex items-center gap-1">
              <span>🔥</span>
              <span class="text-sm" style="color: #F4A620; font-weight: 700">{{ student.streak_count }}</span>
            </div>

            <!-- Avg Score -->
            <div class="text-sm" style="font-weight: 700" :style="{ color: scoreColor(student.recent_avg) }">
              {{ student.recent_avg !== null ? student.recent_avg.toFixed(1) : '-' }}
            </div>

            <!-- Mini Chart (CSS bars) -->
            <div class="flex items-end gap-0.5 h-8">
              <div
                v-for="(item, i) in student.score_history.slice(-7)"
                :key="i"
                class="flex-1 rounded-sm"
                :style="{
                  height: (item.avg_score / 10 * 100) + '%',
                  backgroundColor: student.needs_attention ? '#FCA5A5' : '#4170CC',
                  minHeight: '2px',
                }"
              />
            </div>

            <!-- Arrow -->
            <div class="hidden md:flex justify-end">
              <ChevronRight :size="16" color="#C0D0F6" />
            </div>
          </div>

          <div v-if="filteredStudents.length === 0" class="px-5 py-10 text-center text-sm" style="color: #93B2E8">
            해당하는 학생이 없어요
          </div>
        </div>
      </div>
    </div>

    <!-- Student Detail Modal -->
    <div
      v-if="selectedStudent"
      class="fixed inset-0 z-50 flex items-center justify-center p-4"
      style="background-color: rgba(4,17,43,0.6); backdrop-filter: blur(4px)"
      @click.self="selectedStudent = null"
    >
      <div
        class="rounded-3xl p-8 w-full max-w-lg"
        style="background-color: white; max-height: 90vh; overflow: auto"
      >
        <!-- Modal Header -->
        <div class="flex items-center justify-between mb-6">
          <div class="flex items-center gap-3">
            <div
              class="w-12 h-12 rounded-full flex items-center justify-center text-white"
              style="background-color: #1B438A; font-size: 18px; font-weight: 700"
            >
              {{ selectedStudent.name[0] }}
            </div>
            <div>
              <div style="color: #081830; font-size: 1.1rem; font-weight: 800">{{ selectedStudent.name }}</div>
              <div class="flex items-center gap-2 mt-1">
                <span
                  class="px-2.5 py-1 rounded-lg text-xs"
                  :style="{ backgroundColor: levelColors[(selectedStudent.level as 1|2|3)].bg, color: levelColors[(selectedStudent.level as 1|2|3)].text, fontWeight: 700 }"
                >
                  {{ levelLabels[(selectedStudent.level as 1|2|3)] }}급
                </span>
                <span class="text-xs" style="color: #93B2E8">🔥 {{ selectedStudent.streak_count }}일</span>
              </div>
            </div>
          </div>
          <button @click="selectedStudent = null" style="color: #93B2E8; font-size: 20px">✕</button>
        </div>

        <div class="space-y-4">
          <!-- Score History Chart -->
          <div class="rounded-2xl p-5" style="background-color: #F8FAFF; border: 1px solid #EBF0FC">
            <div class="text-xs mb-3" style="color: #93B2E8; font-weight: 700; text-transform: uppercase">4주 점수 추이</div>
            <div class="flex items-end gap-1" style="height: 80px">
              <template v-if="selectedStudent.score_history.length > 0">
                <div
                  v-for="(item, i) in selectedStudent.score_history"
                  :key="i"
                  class="flex-1 flex flex-col items-center gap-1"
                >
                  <div
                    class="w-full rounded-t"
                    :style="{ height: (item.avg_score / 10 * 64) + 'px', backgroundColor: '#1B438A', minHeight: '2px' }"
                  />
                  <span style="color: #93B2E8; font-size: 9px">{{ formatDateShort(item.date) }}</span>
                </div>
              </template>
              <div v-else class="flex-1 text-xs text-center self-center" style="color: #C0D0F6">세션 기록 없음</div>
            </div>
          </div>

          <!-- Weak Areas -->
          <div
            v-if="selectedStudent.weak_areas.length > 0"
            class="rounded-2xl p-4"
            style="background-color: #FEF2F2; border: 1px solid #FECACA"
          >
            <div class="text-xs mb-2" style="color: #991B1B; font-weight: 700">⚠️ 취약 영역</div>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="area in selectedStudent.weak_areas"
                :key="area"
                class="px-3 py-1.5 rounded-xl text-sm"
                style="background-color: #FEE2E2; color: #B91C1C; font-weight: 600"
              >
                {{ area }}
              </span>
            </div>
          </div>

          <!-- Level Override -->
          <div class="rounded-2xl p-4" style="background-color: #F8FAFF; border: 1px solid #EBF0FC">
            <div class="text-xs mb-3" style="color: #5A7AB8; font-weight: 700">✏️ 난이도 수동 조정</div>
            <div class="flex gap-2">
              <button
                v-for="l in ([1, 2, 3] as Array<1|2|3>)"
                :key="l"
                @click="setLevel(selectedStudent, l)"
                class="flex-1 py-3 rounded-xl text-sm transition-all"
                :style="{
                  backgroundColor: selectedStudent.level === l ? levelColors[l].text : levelColors[l].bg,
                  color: selectedStudent.level === l ? 'white' : levelColors[l].text,
                  fontWeight: 700,
                }"
              >
                {{ levelLabels[l] }}급
              </button>
            </div>
            <p class="text-xs mt-2" style="color: #93B2E8">수동 설정 시 AI 자동 재조정이 비활성화돼요</p>
          </div>
        </div>

        <button
          @click="selectedStudent = null"
          class="w-full mt-5 py-3.5 rounded-xl text-sm"
          style="background-color: #EBF0FC; color: #1B438A; font-weight: 700"
        >
          닫기
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-vue-next'
import apiClient from '@/api/client'

const router = useRouter()
const route = useRoute()
const classroomId = route.params.classroomId as string

// ── Types ─────────────────────────────────────────────────────────────────────
interface ScoreHistory {
  date: string
  avg_score: number
}
interface StudentItem {
  id: string
  name: string
  level: number
  teacher_override_level: number | null
  weak_areas: string[]
  streak_count: number
  recent_avg: number | null
  needs_attention: boolean
  score_history: ScoreHistory[]
}
interface Dashboard {
  classroom_name: string
  students: StudentItem[]
}

// ── State ─────────────────────────────────────────────────────────────────────
const dashboard = ref<Dashboard | null>(null)
const loading = ref(true)
const activeFilter = ref<'all' | 'attention' | 'high' | 'mid' | 'low'>('all')
const editingLevelId = ref<string | null>(null)
const selectedStudent = ref<StudentItem | null>(null)

// ── Constants ─────────────────────────────────────────────────────────────────
const levelLabels: Record<1 | 2 | 3, string> = { 1: '하', 2: '중', 3: '상' }
const levelColors: Record<1 | 2 | 3, { bg: string; text: string }> = {
  1: { bg: '#FEE2E2', text: '#B91C1C' },
  2: { bg: '#FEF3C7', text: '#92400E' },
  3: { bg: '#D1FAE5', text: '#065F46' },
}

// ── Computed ──────────────────────────────────────────────────────────────────
const students = computed(() => dashboard.value?.students ?? [])

const attentionCount = computed(() => students.value.filter(s => s.needs_attention).length)

const statsGrid = computed(() => {
  const s = students.value
  const withAvg = s.filter(x => x.recent_avg !== null)
  const avgScore = withAvg.length
    ? withAvg.reduce((acc, x) => acc + (x.recent_avg ?? 0), 0) / withAvg.length
    : 0
  const streakAvg = s.length ? s.reduce((acc, x) => acc + x.streak_count, 0) / s.length : 0
  return [
    { emoji: '👥', label: '전체 학생', value: s.length, unit: '명', sub: '' },
    { emoji: '📚', label: '오늘 학습', value: '-', unit: '명', sub: '오늘 참여' },
    { emoji: '⭐', label: '평균 점수', value: avgScore.toFixed(1), unit: '점', sub: '최근 3세션' },
    { emoji: '🔥', label: '평균 streak', value: streakAvg.toFixed(1), unit: '일', sub: '' },
  ]
})

const filterTabs = computed(() => {
  const s = students.value
  return [
    { key: 'all' as const, label: `전체 (${s.length})` },
    { key: 'attention' as const, label: `⚠️ 주의 (${attentionCount.value})` },
    { key: 'high' as const, label: `상급 (${s.filter(x => x.level === 3).length})` },
    { key: 'mid' as const, label: `중급 (${s.filter(x => x.level === 2).length})` },
    { key: 'low' as const, label: `하급 (${s.filter(x => x.level === 1).length})` },
  ]
})

const filteredStudents = computed(() => {
  const s = students.value
  if (activeFilter.value === 'all') return s
  if (activeFilter.value === 'attention') return s.filter(x => x.needs_attention)
  if (activeFilter.value === 'high') return s.filter(x => x.level === 3)
  if (activeFilter.value === 'mid') return s.filter(x => x.level === 2)
  if (activeFilter.value === 'low') return s.filter(x => x.level === 1)
  return s
})

// ── Helpers ───────────────────────────────────────────────────────────────────
function levelCount(level: 1 | 2 | 3) {
  return students.value.filter(s => s.level === level).length
}

function levelPct(level: 1 | 2 | 3) {
  return students.value.length
    ? Math.round((levelCount(level) / students.value.length) * 100)
    : 0
}

function scoreColor(avg: number | null) {
  if (avg === null) return '#93B2E8'
  if (avg >= 7) return '#16A34A'
  if (avg >= 5) return '#D97706'
  return '#DC2626'
}

function formatDateShort(date: string) {
  const d = new Date(date)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

// ── Actions ───────────────────────────────────────────────────────────────────
function openModal(student: StudentItem) {
  selectedStudent.value = { ...student, score_history: [...student.score_history] }
  editingLevelId.value = null
}

function toggleLevelEdit(id: string) {
  editingLevelId.value = editingLevelId.value === id ? null : id
}

async function setLevel(student: StudentItem, level: 1 | 2 | 3) {
  try {
    await apiClient.patch(`/teacher/students/${student.id}/level`, { level })
    if (dashboard.value) {
      const target = dashboard.value.students.find(s => s.id === student.id)
      if (target) {
        target.level = level
        target.teacher_override_level = level
      }
    }
    if (selectedStudent.value?.id === student.id) {
      selectedStudent.value = { ...selectedStudent.value, level, teacher_override_level: level }
    }
    editingLevelId.value = null
  } catch {
    // silent
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const res = await apiClient.get(`/teacher/classrooms/${classroomId}/dashboard`)
    dashboard.value = res.data
  } finally {
    loading.value = false
  }
})
</script>
