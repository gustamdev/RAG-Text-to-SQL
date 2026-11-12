import { createSSEParser } from '../lib/sse'
import type { AgentEvent, AskResponse, Feedback } from '../types/chat'
import { API_BASE, ApiError, api, notifyUnauthorized, tokenStore } from './http'

const INTERRUPTED = 'A conexão com o servidor foi interrompida.'
const BAD_EVENT = 'Evento do servidor em formato inesperado.'

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

export function isAgentEvent(data: unknown): data is AgentEvent {
  return (
    typeof data === 'object' &&
    data !== null &&
    'node' in data &&
    'label' in data &&
    'done' in data &&
    typeof data.done === 'boolean'
  )
}

/** Mensagem em português para os erros do chat (o `detail` do backend nem sempre está em português). */
export function chatErrorMessage(status: number, fallback?: string): string {
  switch (status) {
    case 401:
      return 'Sua sessão expirou. Entre novamente no backoffice.'
    case 403:
      return 'Você não tem permissão para usar o assistente.'
    case 404:
      return 'Pergunta não encontrada. Envie a pergunta de novo.'
    case 429:
      return 'Muitas perguntas em pouco tempo. Aguarde um instante e tente de novo.'
    default:
      return fallback ?? 'Não foi possível obter a resposta. Tente novamente.'
  }
}

/** Reescreve o ApiError com a mensagem do chat; outros erros (ex.: abort) passam intactos. */
async function chatRequest<T>(run: () => Promise<T>): Promise<T> {
  try {
    return await run()
  } catch (error) {
    if (error instanceof ApiError && [401, 403, 404, 429].includes(error.status)) {
      throw new ApiError(error.status, chatErrorMessage(error.status))
    }
    throw error
  }
}

/**
 * POST: envia a pergunta e devolve o id da execução (o grafo já começa a rodar no backend).
 * Exige sessão de administrador (Bearer, via `api`).
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
  const data = await chatRequest(() =>
    api<unknown>('/chat/questions', {
      method: 'POST',
      body: { question, session_id: sessionId },
      ...(signal ? { signal } : {}),
    }),
  )
  if (!isAskResponse(data)) throw new Error('Resposta do servidor em formato inesperado.')
  return data
}

/** POST: thumbs up/down da última resposta — vira uma linha do golden dataset no backend. */
export async function sendFeedback(
  questionId: string,
  params: { sessionId: string; question: string; answer: string; feedback: Feedback },
  signal?: AbortSignal,
): Promise<void> {
  await chatRequest(() =>
    api<void>(`/chat/questions/${encodeURIComponent(questionId)}/feedback`, {
      method: 'POST',
      body: {
        session_id: params.sessionId,
        question: params.question,
        answer: params.answer,
        is_approved: params.feedback === 'up',
      },
      ...(signal ? { signal } : {}),
    }),
  )
}

/**
 * GET: acompanha a execução por SSE, um evento por nó do grafo, até o evento final
 * (`done: true`). Usa fetch + ReadableStream (e não EventSource) para poder mandar o
 * header Authorization. Devolve uma função para fechar a conexão antes do fim, se precisar.
 *
 * `onError` é chamado no máximo uma vez, e nunca depois de `done` nem depois de o chamador fechar.
 */
export function streamQuestionEvents(
  questionId: string,
  onEvent: (event: AgentEvent) => void,
  onError: (error: Error) => void,
): () => void {
  const controller = new AbortController()
  let finished = false

  const finish = (error?: Error) => {
    if (finished) return
    finished = true
    controller.abort()
    if (error) onError(error)
  }

  const run = async () => {
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    const token = tokenStore.get()
    if (token) headers['Authorization'] = `Bearer ${token}`

    const response = await fetch(`${API_BASE}/chat/questions/${encodeURIComponent(questionId)}/events`, {
      headers,
      signal: controller.signal,
    })

    if (!response.ok) {
      if (response.status === 401 && token) notifyUnauthorized()
      return finish(new Error(chatErrorMessage(response.status, INTERRUPTED)))
    }
    if (!response.body) return finish(new Error(INTERRUPTED))

    const parser = createSSEParser((message) => {
      if (finished) return
      if (message.event === 'error') return finish(new Error(INTERRUPTED))

      let payload: unknown
      try {
        payload = JSON.parse(message.data)
      } catch {
        return finish(new Error(BAD_EVENT))
      }
      if (!isAgentEvent(payload)) return finish(new Error(BAD_EVENT))

      onEvent(payload)
      if (payload.done) finish()
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    while (!finished) {
      const { done, value } = await reader.read()
      if (done) break
      parser.push(decoder.decode(value, { stream: true }))
    }
    // Stream acabou sem o evento final: a conexão caiu no meio.
    if (!finished) finish(new Error(INTERRUPTED))
  }

  run().catch(() => {
    // Abort nosso (done ou close) não é erro; qualquer outra falha é desconexão.
    if (!finished) finish(new Error(INTERRUPTED))
  })

  return () => {
    finished = true
    controller.abort()
  }
}
