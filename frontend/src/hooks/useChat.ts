import { useCallback, useEffect, useRef, useState } from 'react'
import { askQuestion, sendFeedback as postFeedback, streamQuestionEvents } from '../services/chat'
import type { ChatMessage, ChatStatus, Feedback } from '../types/chat'

const FALLBACK_ERROR = 'Não foi possível obter a resposta. Tente novamente.'

function createMessage(role: ChatMessage['role'], content: string, isError = false): ChatMessage {
  return { id: crypto.randomUUID(), role, content, isError }
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [status, setStatus] = useState<ChatStatus>('idle')
  const abortRef = useRef<AbortController | null>(null)
  const closeStreamRef = useRef<(() => void) | null>(null)
  // Persiste entre perguntas (mesma aba) para dar continuidade à conversa — a memória de
  // sessão vive no backend, por session_id; aqui só guardamos o id para reenviar.
  const sessionIdRef = useRef<string | null>(null)

  useEffect(
    () => () => {
      abortRef.current?.abort()
      closeStreamRef.current?.()
    },
    [],
  )

  const patchMessage = useCallback((id: string, patch: Partial<ChatMessage> | ((m: ChatMessage) => ChatMessage)) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === id
          ? typeof patch === 'function'
            ? patch(message)
            : { ...message, ...patch }
          : message,
      ),
    )
  }, [])

  const send = useCallback(
    async (text: string) => {
      const content = text.trim()
      if (!content || status === 'loading') return

      const controller = new AbortController()
      abortRef.current = controller

      const assistant = createMessage('assistant', '')
      assistant.steps = []
      setMessages((current) => [...current, createMessage('user', content), assistant])
      setStatus('loading')

      try {
        const { question_id: questionId, session_id: sessionId } = await askQuestion(
          content,
          sessionIdRef.current ?? undefined,
          controller.signal,
        )
        sessionIdRef.current = sessionId
        patchMessage(assistant.id, { questionId, sessionId, question: content })
        if (controller.signal.aborted) return

        await new Promise<void>((resolve) => {
          closeStreamRef.current = streamQuestionEvents(
            questionId,
            (event) => {
              if (event.done) {
                patchMessage(assistant.id, { content: event.answer ?? '' })
                resolve()
                return
              }
              patchMessage(assistant.id, (message) => ({
                ...message,
                steps: [...(message.steps ?? []), { node: event.node, label: event.label, detail: event.detail }],
              }))
            },
            (error) => {
              patchMessage(assistant.id, { content: error.message, isError: true })
              resolve()
            },
          )
        })
      } catch (error) {
        if (controller.signal.aborted) return
        const detail = error instanceof Error ? error.message : FALLBACK_ERROR
        patchMessage(assistant.id, { content: detail, isError: true })
      } finally {
        closeStreamRef.current = null
        if (!controller.signal.aborted) setStatus('idle')
      }
    },
    [status, patchMessage],
  )

  const sendFeedback = useCallback(
    (messageId: string, feedback: Feedback) => {
      const message = messages.find((m) => m.id === messageId)
      if (!message?.questionId || !message.sessionId || message.question === undefined) return

      patchMessage(messageId, { feedback })
      postFeedback(message.questionId, {
        sessionId: message.sessionId,
        question: message.question,
        answer: message.content,
        feedback,
      }).catch(() => {
        // Feedback é um extra: uma falha aqui não deve incomodar quem só queria avaliar a resposta.
      })
    },
    [messages, patchMessage],
  )

  return { messages, status, send, sendFeedback }
}
