import './App.css'
import { Composer } from './components/Composer'
import { MessageList } from './components/MessageList'
import { useChat } from './hooks/useChat'

function App() {
  const { messages, status, send, sendFeedback } = useChat()
  const isEmpty = messages.length === 0 && status === 'idle'

  return (
    <div className="chat">
      <header className="chat__header">
        <h1 className="chat__title">Assistente RAG</h1>
      </header>

      <main className="chat__body">
        <div className="container">
          {isEmpty ? (
            <div className="empty">
              <h2 className="empty__title">Pergunte sobre os dados</h2>
              <p className="empty__hint">
                Faça perguntas sobre os pedidos do marketplace Olist em 2018.
              </p>
            </div>
          ) : (
            <MessageList messages={messages} status={status} onFeedback={sendFeedback} />
          )}
        </div>
      </main>

      <footer className="chat__footer">
        <div className="container">
          <Composer disabled={status === 'loading'} onSubmit={send} />
        </div>
      </footer>
    </div>
  )
}

export default App
