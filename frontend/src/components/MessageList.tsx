import { useEffect, useRef } from 'react'
import type { ChatMessage, ChatStatus, Feedback } from '../types/chat'

interface MessageListProps {
  messages: ChatMessage[]
  status: ChatStatus
  onFeedback: (messageId: string, feedback: Feedback) => void
}

function AgentSteps({ steps }: { steps: ChatMessage['steps'] }) {
  if (!steps || steps.length === 0) return null

  return (
    <ol className="message__steps" aria-label="Etapas da consulta">
      {steps.map((step, index) => (
        <li key={`${step.node}-${index}`} className="message__step">
          <span className="message__step-label">{step.label}</span>
          {step.detail && <span className="message__step-detail">{step.detail}</span>}
        </li>
      ))}
    </ol>
  )
}

function FeedbackButtons({ message, onFeedback }: { message: ChatMessage; onFeedback: MessageListProps['onFeedback'] }) {
  if (message.feedback) {
    return <p className="message__feedback-thanks">Obrigado pelo feedback!</p>
  }

  return (
    <div className="message__feedback" role="group" aria-label="Avaliar esta resposta">
      <button
        type="button"
        className="message__feedback-button"
        aria-label="Resposta útil"
        onClick={() => onFeedback(message.id, 'up')}
      >
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
          <path
            d="M7 18v-9l4-6 1 1-1 5h5.5a1.5 1.5 0 0 1 1.46 1.84l-1.5 6A1.5 1.5 0 0 1 15 18H7Zm-2-9H3v9h2V9Z"
            fill="currentColor"
          />
        </svg>
      </button>
      <button
        type="button"
        className="message__feedback-button"
        aria-label="Resposta não útil"
        onClick={() => onFeedback(message.id, 'down')}
      >
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
          <path
            d="M13 2v9l-4 6-1-1 1-5H3.5A1.5 1.5 0 0 1 2.04 9.16l1.5-6A1.5 1.5 0 0 1 5 2h8Zm2 9h2V2h-2v9Z"
            fill="currentColor"
          />
        </svg>
      </button>
    </div>
  )
}

export const MessageList = ({ messages, status, onFeedback }: MessageListProps) => {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    endRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [messages, status])

  const lastMessageId = messages.at(-1)?.id

  return (
    <ol className="messages" aria-live="polite" aria-label="Conversa">
      {messages.map((message) => {
        const isPending = status === 'loading' && !message.content && !message.isError
        // Só a última resposta do assistente recebe os thumbs, e só quando ela já chegou.
        const canRateIt =
          message.role === 'assistant' && message.id === lastMessageId && message.content && !message.isError

        return (
          <li key={message.id} className="message" data-role={message.role} data-error={message.isError || undefined}>
            <div className="message__bubble">
              {message.role === 'assistant' && <AgentSteps steps={message.steps} />}
              {message.content && <p className="message__text">{message.content}</p>}
              {isPending && (
                <p className="message__text typing" role="status">
                  <span className="visually-hidden">Gerando resposta</span>
                  <span className="typing__dot" aria-hidden="true" />
                  <span className="typing__dot" aria-hidden="true" />
                  <span className="typing__dot" aria-hidden="true" />
                </p>
              )}
              {canRateIt && <FeedbackButtons message={message} onFeedback={onFeedback} />}
            </div>
          </li>
        )
      })}
      <div ref={endRef} />
    </ol>
  )
}
