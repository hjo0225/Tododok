import { defineStore } from 'pinia'
import { ref } from 'vue'

interface Passage {
  title: string
  genre: string
  difficulty: number
  content: string
}

interface Question {
  index: number
  type: 'info' | 'reasoning' | 'vocabulary'
  text: string
  choices: string[]
}

export type SessionPhase = 'idle' | 'reading' | 'mcq' | 'done'

export const useSessionStore = defineStore('session', () => {
  const sessionId = ref<string | null>(null)
  const passage = ref<Passage | null>(null)
  const questions = ref<Question[]>([])
  const currentQuestionIndex = ref(0) // 0-based
  const answers = ref<(number | null)[]>([null, null, null])
  const phase = ref<SessionPhase>('idle')

  function startSession(data: {
    session_id: string
    passage: Passage
    questions: Question[]
  }) {
    sessionId.value = data.session_id
    passage.value = data.passage
    questions.value = data.questions
    currentQuestionIndex.value = 0
    answers.value = [null, null, null]
    phase.value = 'reading'
  }

  function goToMcq() {
    phase.value = 'mcq'
  }

  function recordAnswer(questionIndex: number, selectedIndex: number) {
    answers.value[questionIndex] = selectedIndex
  }

  function nextQuestion() {
    if (currentQuestionIndex.value < 2) {
      currentQuestionIndex.value++
    } else {
      phase.value = 'done'
    }
  }

  function reset() {
    sessionId.value = null
    passage.value = null
    questions.value = []
    currentQuestionIndex.value = 0
    answers.value = [null, null, null]
    phase.value = 'idle'
  }

  return {
    sessionId,
    passage,
    questions,
    currentQuestionIndex,
    answers,
    phase,
    startSession,
    goToMcq,
    recordAnswer,
    nextQuestion,
    reset,
  }
})
