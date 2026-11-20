import type { ThreadSummary } from '../../types/chat'

interface ThreadSidebarProps {
  threads: ThreadSummary[]
  activeId: string | null
  onNew: () => void
  onOpen: (sessionId: string) => void
  onDelete: (sessionId: string) => void
}

/** Segunda sidebar do assistente: lista de conversas salvas + "Novo chat". */
export function ThreadSidebar({ threads, activeId, onNew, onOpen, onDelete }: ThreadSidebarProps) {
  return (
    <nav className="threads" aria-label="Conversas">
      <button type="button" className="threads__new" onClick={onNew}>
        + Novo chat
      </button>
      <ul className="threads__list">
        {threads.map((thread) => (
          <li key={thread.session_id} className="threads__item" data-active={thread.session_id === activeId || undefined}>
            <button type="button" className="threads__open" onClick={() => onOpen(thread.session_id)} title={thread.title}>
              {thread.title}
            </button>
            <button
              type="button"
              className="threads__delete"
              aria-label={`Excluir conversa: ${thread.title}`}
              onClick={() => onDelete(thread.session_id)}
            >
              ×
            </button>
          </li>
        ))}
        {threads.length === 0 && <li className="threads__empty">Nenhuma conversa ainda.</li>}
      </ul>
    </nav>
  )
}
