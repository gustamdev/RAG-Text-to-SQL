import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentEvent } from '../types/chat'
import { chatErrorMessage, streamQuestionEvents } from './chat'
import { tokenStore } from './http'

const enc = new TextEncoder()

function sseResponse(chunks: string[], status = 200): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(enc.encode(chunk))
      controller.close()
    },
  })
  return new Response(status === 200 ? stream : null, { status })
}

const step = (node: string, done = false, answer: string | null = null) =>
  `data: ${JSON.stringify({ node, label: node, detail: null, done, answer })}\n\n`

function run(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  tokenStore.set('tok')
  return new Promise<{ events: AgentEvent[]; error: Error | null; headers: Headers }>((resolve) => {
    const events: AgentEvent[] = []
    let settled = false
    const finish = (error: Error | null) => {
      if (settled) return
      settled = true
      const init = fetchMock.mock.calls[0]?.[1] as RequestInit
      resolve({ events, error, headers: new Headers(init.headers) })
    }
    streamQuestionEvents(
      'q1',
      (e) => {
        events.push(e)
        if (e.done) setTimeout(() => finish(null), 0)
      },
      (err) => finish(err),
    )
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  tokenStore.clear()
})

describe('streamQuestionEvents', () => {
  it('manda Bearer e entrega os eventos até o done, mesmo com chunks partidos', async () => {
    const full = step('a') + step('b', true, 'resposta')
    const result = await run(sseResponse([full.slice(0, 20), full.slice(20, 90), full.slice(90)]))
    expect(result.headers.get('Authorization')).toBe('Bearer tok')
    expect(result.error).toBeNull()
    expect(result.events.map((e) => e.node)).toEqual(['a', 'b'])
    expect(result.events.at(-1)?.answer).toBe('resposta')
  })

  it('stream que acaba sem done vira erro de conexão', async () => {
    const result = await run(sseResponse([step('a')]))
    expect(result.events).toHaveLength(1)
    expect(result.error?.message).toMatch(/interrompida/)
  })

  it('evento fora do formato vira erro', async () => {
    const result = await run(sseResponse(['data: nao-json\n\n']))
    expect(result.error?.message).toMatch(/formato inesperado/)
  })

  it.each([
    [403, /permissão/],
    [404, /não encontrada/],
    [429, /Muitas perguntas/],
  ])('HTTP %i vira mensagem em português', async (status, pattern) => {
    const result = await run(sseResponse([], status))
    expect(result.error?.message).toMatch(pattern)
  })
})

describe('chatErrorMessage', () => {
  it('usa o fallback para status desconhecidos', () => {
    expect(chatErrorMessage(500, 'x')).toBe('x')
    expect(chatErrorMessage(401)).toMatch(/sessão/i)
  })
})
