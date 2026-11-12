import { useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, KeyboardEvent } from 'react'

interface ComposerProps {
  disabled: boolean
  onSubmit: (text: string) => void
}

export const Composer = ({ disabled, onSubmit }: ComposerProps) => {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const canSend = value.trim().length > 0 && !disabled

  const resize = () => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${element.scrollHeight}px`
  }

  const submit = () => {
    if (!canSend) return
    onSubmit(value)
    setValue('')
    requestAnimationFrame(resize)
  }

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setValue(event.target.value)
    resize()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    submit()
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label className="visually-hidden" htmlFor="chat-input">
        Mensagem
      </label>
      <textarea
        id="chat-input"
        ref={textareaRef}
        className="composer__input"
        rows={1}
        value={value}
        placeholder="Escreva sua pergunta"
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        autoFocus
      />
      <button
        type="submit"
        className="composer__send"
        disabled={!canSend}
        aria-label="Enviar mensagem"
      >
        <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
          <path
            d="M10 16V4m0 0L5 9m5-5 5 5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </form>
  )
}
