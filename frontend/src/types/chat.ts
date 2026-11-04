export type MessageRole = 'user' | 'assistant'

/** Um passo do grafo do agente (POST .../events), na ordem em que chegam. */
export interface AgentStep {
  node: string
  label: string
  detail: string | null
}

export type Feedback = 'up' | 'down'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  isError?: boolean
  /** Só em mensagens do assistente: a trilha de passos do grafo até a resposta. */
  steps?: AgentStep[]
  /** Só em mensagens do assistente: dados para o thumbs up/down (POST .../feedback). */
  questionId?: string
  sessionId?: string
  question?: string
  feedback?: Feedback
}

export type ChatStatus = 'idle' | 'loading'

/** Corpo esperado de POST /api/v1/chat/questions. */
export interface AskResponse {
  question_id: string
  session_id: string
}

/** Uma linha do stream GET /api/v1/chat/questions/{id}/events. */
export interface AgentEvent {
  node: string
  label: string
  detail: string | null
  done: boolean
  answer: string | null
}
