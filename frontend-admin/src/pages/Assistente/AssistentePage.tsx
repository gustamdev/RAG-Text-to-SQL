import { Composer } from '@/components/chat/Composer'
import { ThreadSidebar } from '@/components/chat/ThreadSidebar'
import { MessageList } from '@/components/chat/MessageList'
import { useChat } from '@/hooks/useChat'
import { usePageTitle } from '@/hooks/usePageTitle'
import './assistente.css'

const EXAMPLES = [
  'Quais as 10 categorias com maior receita?',
  'Qual a nota média por estado do vendedor?',
  'Quantos pedidos foram entregues com atraso por mês?',
]

/**
 * Assistente Text-to-SQL (agente LangGraph) dentro do backoffice. CSS próprio isolado em `.assistente`;
 * ocupa toda a altura da área de conteúdo do BackofficeLayout. O backend exige sessão de administrador.
 */
export default function AssistentePage() {
  usePageTitle('Assistente de dados')
  const { messages, status, send, sendFeedback, threads, activeId, newChat, openThread, removeThread } = useChat()
  const isEmpty = messages.length === 0 && status === 'idle'

  return (
    <div className="assistente">
      <ThreadSidebar
        threads={threads}
        activeId={activeId}
        onNew={newChat}
        onOpen={(id) => void openThread(id)}
        onDelete={(id) => void removeThread(id)}
      />
      <div className="chat">
        <header className="chat__header">
          <h1 className="chat__title">Assistente de dados</h1>
        </header>

        <div className="chat__body">
          <div className="container">
            {isEmpty ? (
              <div className="empty">
                <h2 className="empty__title">Pergunte sobre os dados</h2>
                <p className="empty__hint">
                  Faça perguntas sobre produtos, categorias, notas e vendas do Olist. O assistente consulta o banco e
                  responde em linguagem natural.
                </p>
                <div className="empty__examples" role="group" aria-label="Perguntas de exemplo">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example}
                      type="button"
                      className="empty__example"
                      onClick={() => void send(example)}
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <MessageList messages={messages} status={status} onFeedback={sendFeedback} />
            )}
          </div>
        </div>

        <footer className="chat__footer">
          <div className="container">
            <Composer disabled={status === 'loading'} onSubmit={send} />
          </div>
        </footer>
      </div>
    </div>
  )
}
