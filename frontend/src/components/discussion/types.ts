export type Speaker = 'moderator' | 'peer_a' | 'peer_b' | 'user'

export interface DisplayMessage {
  id: number
  speaker: Speaker
  content: string
  round: number
}

export const SPEAKERS: Record<Speaker, { name: string; emoji: string; color: string; bg: string; textColor: string }> = {
  moderator: { name: '모더레이터', emoji: 'M', color: '#7C3AED', bg: '#EDE9FE', textColor: '#5B21B6' },
  peer_a:    { name: '민지',       emoji: 'A', color: '#059669', bg: '#D1FAE5', textColor: '#065F46' },
  peer_b:    { name: '준서',       emoji: 'B', color: '#D97706', bg: '#FEF3C7', textColor: '#92400E' },
  user:      { name: '나',         emoji: '나', color: '#1B438A', bg: '#EBF0FC', textColor: '#081830' },
}
