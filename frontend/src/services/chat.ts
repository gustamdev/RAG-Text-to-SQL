import type { AgentEvent, AskResponse, Feedback } from '../types/chat'

const API_BASE = '/api/v1'

function isAskResponse(data: unknown): data is AskResponse {
  return (
    typeof data === 'object' &&
    data !== null &&
    'question_id' in data &&
    typeof data.question_id === 'string' &&
    'session_id' in data &&
    typeof data.session_id === 'string'
  )
}

function isAgentEvent(data: unknown): data is AgentEvent {
  return (
    typeof data === 'object' &&
    data !== null &&
    'node' in data &&
    'label' in data &&
    'done' in data &&
    typeof data.done === 'boolean'
  )
}

/**
 * POST: envia a pergunta e devolve o id da execução (o grafo já começa a rodar no backend).
 *
 * `sessionId`: reenvie o da resposta anterior para dar continuidade à conversa (memória de
 * sessão no backend); omita (`undefined`) para começar uma conversa nova. A resposta sempre
 * traz um `session_id` — gerado pelo servidor se nenhum foi mandado.
 */
export async function askQuestion(
  question: string,
  sessionId?: string,
  signal?: AbortSignal,
): Promise<AskResponse> {
  const response = await fetch(`${API_BASE}/chat/questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
    signal,
  })

  if (!response.ok) {
    throw new Error(`O servidor respondeu com erro ${response.status}.`)
  }

  const data: unknown = await response.json()
  if (!isAskResponse(data)) {
    throw new Error('Resposta do servidor em formato inesperado.')
  }

  return data
}

/** POST: thumbs up/down da última resposta — vira uma linha do golden dataset no backend. */
export async function sendFeedback(
  questionId: string,
  params: { sessionId: string; question: string; answer: string; feedback: Feedback },
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/questions/${questionId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: params.sessionId,
      question: params.question,
      answer: params.answer,
      is_approved: params.feedback === 'up',
    }),
    signal,
  })

  if (!response.ok) {
    throw new Error(`O servidor respondeu com erro ${response.status}.`)
  }
}

/**
 * GET: acompanha a execução por SSE, um evento por nó do grafo, até o evento final
 * (`done: true`). Devolve uma função para fechar a conexão antes do fim, se precisar.
 */
export function streamQuestionEvents(
  questionId: string,
  onEvent: (event: AgentEvent) => void,
  onError: (error: Error) => void,
): () => void {
  const source = new EventSource(`${API_BASE}/chat/questions/${questionId}/events`)

  source.onmessage = (message) => {
    let event: unknown
    try {
      event = JSON.parse(message.data)
    } catch {
      source.close()
      onError(new Error('Evento do servidor em formato inesperado.'))
      return
    }
    if (!isAgentEvent(event)) {
      source.close()
      onError(new Error('Evento do servidor em formato inesperado.'))
      return
    }
    if (event.done) source.close()
    onEvent(event)
  }

  // EventSource chama onerror tanto numa falha real quanto depois de um close() nosso;
  // como o close só acontece após o evento done, não há onmessage pendente para confundir.
  source.onerror = () => {
    source.close()
    onError(new Error('A conexão com o servidor foi interrompida.'))
  }

  return () => source.close()
}
