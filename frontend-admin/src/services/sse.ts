/**
 * Parser de Server-Sent Events (text/event-stream) como função pura, sem DOM nem rede.
 * Segue a especificação do WHATWG: blocos separados por linha em branco, linhas `data:` concatenadas
 * com "\n", `event:` e `id:` opcionais, linhas iniciadas por ":" são comentários, `retry:` é ignorado,
 * fim de linha pode ser \n, \r\n ou \r, e um chunk pode terminar no meio de qualquer linha.
 */

export interface SSEMessage {
  /** Valor de `event:`; "message" quando ausente. */
  event: string
  /** Linhas `data:` unidas por "\n". */
  data: string
  /** Valor de `id:`, se houve. */
  id: string | null
}

export interface SSEParser {
  /** Alimenta o parser com o próximo pedaço de texto; chama `onMessage` a cada evento completo. */
  push(chunk: string): void
}

export function createSSEParser(onMessage: (message: SSEMessage) => void): SSEParser {
  let buffer = ''
  let started = false
  let data: string[] = []
  let event = ''
  let id: string | null = null

  function dispatch() {
    // Sem nenhuma linha `data:` o bloco não vira evento (ex.: bloco só com comentário ou `id:`).
    if (data.length > 0) onMessage({ event: event || 'message', data: data.join('\n'), id })
    data = []
    event = ''
    id = null
  }

  function handleLine(line: string) {
    if (line === '') {
      dispatch()
      return
    }
    if (line.startsWith(':')) return // comentário / keep-alive

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'data') data.push(value)
    else if (field === 'event') event = value
    else if (field === 'id') id = value
    // `retry` e campos desconhecidos são ignorados
  }

  return {
    push(chunk) {
      if (!started && chunk.length > 0) {
        started = true
        if (chunk.charCodeAt(0) === 0xfeff) chunk = chunk.slice(1) // BOM
      }
      buffer += chunk

      let start = 0
      for (let i = 0; i < buffer.length; i++) {
        const ch = buffer[i]
        if (ch !== '\n' && ch !== '\r') continue
        if (ch === '\r') {
          // "\r" no fim do buffer pode ser metade de um "\r\n": espera o próximo chunk para decidir.
          if (i === buffer.length - 1) break
          handleLine(buffer.slice(start, i))
          if (buffer[i + 1] === '\n') i++
        } else {
          handleLine(buffer.slice(start, i))
        }
        start = i + 1
      }
      buffer = buffer.slice(start)
    },
  }
}

/** Atalho: parseia um texto completo e devolve os eventos (útil em testes). */
export function parseSSE(text: string): SSEMessage[] {
  const messages: SSEMessage[] = []
  const parser = createSSEParser((m) => messages.push(m))
  parser.push(text)
  // Um "\r" final só é resolvido com mais um byte; um "\n" de fecho descarta a ambiguidade.
  if (text.endsWith('\r')) parser.push('\n')
  return messages
}
