/**
 * useDiscussionStream
 *
 * POST /student/sessions/{id}/discussion 엔드포인트의 SSE 스트림을 관리한다.
 *
 * 설계 메모:
 *  - 브라우저의 EventSource는 GET만 지원하므로 fetch + ReadableStream 방식 사용.
 *  - 네트워크 단절 감지 시 3회까지 지수 백오프 재연결 (1s → 2s → 4s).
 *  - 컴포넌트 unmount 시 AbortController로 진행 중인 fetch를 취소.
 *
 * 수신하는 11가지 이벤트 유형:
 *  1. turn_start    — AI 발화 시작
 *  2. token         — 텍스트 토큰 단위
 *  3. turn_end      — AI 발화 완료
 *  4. wait_for_user — 학생 입력 대기
 *  5. is_final      — 토의 세션 종료
 *  6. error         — 서버 측 오류
 *  7. legacy_msg    — 구형 단일 이벤트 (moderator close 발화)
 *  8. heartbeat     — keepalive (무시)
 *  9. ping          — keepalive (무시)
 * 10. connected     — 연결 시작 알림 (무시)
 * 11. unknown       — 미지 이벤트 (무시)
 */

import { onUnmounted } from 'vue'
import { useDiscussionStore } from '@/stores/discussion'
import { useStudentStore } from '@/stores/student'
import { API_BASE_URL } from '@/api/config'

const MAX_RETRIES = 3
const BACKOFF_BASE_MS = 1_000   // 1s → 2s → 4s

export function useDiscussionStream(sessionId: string) {
  const ds = useDiscussionStore()
  const studentStore = useStudentStore()

  let abort: AbortController | null = null
  let retryCount = 0
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let destroyed = false
  let _retryContent = ''   // 재연결 시 재전송할 마지막 userContent

  // ── SSE 라인 디스패처 ─────────────────────────────────────────
  function dispatch(raw: string) {
    let ev: Record<string, unknown>
    try { ev = JSON.parse(raw) } catch { return }

    if (ev.event === 'turn_start') {
      // 1
      ds.onTurnStart(ev.speaker as any, ev.turn_id as string, ev.round as number)
    } else if (ev.event === 'token') {
      // 2
      ds.onToken(ev.text as string)
    } else if (ev.event === 'turn_end') {
      // 3
      ds.onTurnEnd(ev.full_text as string, ev.round as number)
    } else if (ev.next_speaker === 'user') {
      // 4: wait_for_user
      ds.onWaitForUser(ev.round as number)
    } else if (ev.is_final) {
      // 5
      ds.onFinal()
    } else if (ev.error) {
      // 6
      ds.onError(typeof ev.error === 'string' ? ev.error : undefined)
    } else if (ev.speaker && ev.content) {
      // 7: legacy close message
      ds.onLegacyMessage(ev.speaker as any, ev.content as string, ev.round as number)
    }
    // 8~11: heartbeat / ping / connected / unknown → 무시
  }

  // ── 스트림 읽기 ───────────────────────────────────────────────
  async function _readStream(response: Response): Promise<'done' | 'network_error'> {
    if (!response.body) return 'network_error'
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) return 'done'

        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw) dispatch(raw)
        }
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') return 'done'
      return 'network_error'
    } finally {
      reader.releaseLock()
    }
  }

  // ── 연결 ──────────────────────────────────────────────────────
  async function connect(userContent = '') {
    if (destroyed) return
    _retryContent = userContent

    abort?.abort()
    abort = new AbortController()
    ds.startLoading()

    const token = studentStore.token
    let response: Response

    try {
      response = await fetch(
        `${API_BASE_URL}/student/sessions/${sessionId}/discussion`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ content: userContent }),
          signal: abort.signal,
        },
      )
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      _scheduleRetry()
      return
    }

    if (!response.ok) {
      ds.onError()
      return
    }

    const result = await _readStream(response)
    if (result === 'network_error' && !destroyed) {
      _scheduleRetry()
    } else {
      retryCount = 0
    }
  }

  // ── 지수 백오프 재연결 ────────────────────────────────────────
  function _scheduleRetry() {
    if (destroyed || retryCount >= MAX_RETRIES) {
      ds.onError('연결이 끊어졌어요. 새로고침 후 다시 시도해주세요.')
      return
    }
    const delay = BACKOFF_BASE_MS * Math.pow(2, retryCount)  // 1s, 2s, 4s
    retryCount++
    retryTimer = setTimeout(() => { if (!destroyed) connect(_retryContent) }, delay)
  }

  // ── 연결 해제 ─────────────────────────────────────────────────
  function disconnect() {
    destroyed = true
    abort?.abort()
    if (retryTimer !== null) { clearTimeout(retryTimer); retryTimer = null }
  }

  onUnmounted(disconnect)

  return { connect, disconnect }
}
