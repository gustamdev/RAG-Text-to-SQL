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

/** Item da lista de conversas (GET /api/v1/chat/threads). */
export interface ThreadSummary {
  session_id: string
  title: string
  updated_at: string
}

/** Conversa completa (GET /api/v1/chat/threads/{session_id}): cada item é uma pergunta + resposta. */
export interface ThreadDetail extends ThreadSummary {
  messages: { question_id: string; question: string; answer: string; steps: AgentEvent[] }[]
}
