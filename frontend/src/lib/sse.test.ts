import { describe, expect, it } from 'vitest'
import { createSSEParser, parseSSE, type SSEMessage } from './sse'

function collect(chunks: string[]): SSEMessage[] {
  const out: SSEMessage[] = []
  const parser = createSSEParser((m) => out.push(m))
  for (const chunk of chunks) parser.push(chunk)
  return out
}

describe('parseSSE', () => {
  it('lê um evento simples', () => {
    expect(parseSSE('data: {"a":1}\n\n')).toEqual([{ event: 'message', data: '{"a":1}', id: null }])
  })

  it('lê vários eventos num mesmo chunk', () => {
    const out = parseSSE('data: um\n\ndata: dois\n\ndata: tres\n\n')
    expect(out.map((m) => m.data)).toEqual(['um', 'dois', 'tres'])
  })

  it('aceita \\r\\n e \\r como fim de linha', () => {
    expect(parseSSE('data: a\r\n\r\ndata: b\r\n\r\n').map((m) => m.data)).toEqual(['a', 'b'])
    expect(parseSSE('data: a\r\rdata: b\r\r').map((m) => m.data)).toEqual(['a', 'b'])
  })

  it('junta várias linhas data com \\n', () => {
    expect(parseSSE('data: linha1\ndata: linha2\n\n')[0]?.data).toBe('linha1\nlinha2')
  })

  it('suporta event: e id:', () => {
    expect(parseSSE('event: error\nid: 7\ndata: x\n\n')).toEqual([{ event: 'error', data: 'x', id: '7' }])
  })

  it('ignora comentários, retry e blocos sem data', () => {
    expect(parseSSE(': keep-alive\n\nretry: 1000\n\n: oi\ndata: ok\n\n')).toEqual([
      { event: 'message', data: 'ok', id: null },
    ])
  })

  it('remove só um espaço depois dos dois pontos e aceita data sem espaço', () => {
    expect(parseSSE('data:sem\n\n')[0]?.data).toBe('sem')
    expect(parseSSE('data:  dois\n\n')[0]?.data).toBe(' dois')
  })

  it('data vazio ainda dispara o evento', () => {
    expect(parseSSE('data\n\n')).toEqual([{ event: 'message', data: '', id: null }])
  })

  it('não vaza event/id de um bloco para o próximo', () => {
    const out = parseSSE('event: a\nid: 1\ndata: x\n\ndata: y\n\n')
    expect(out[1]).toEqual({ event: 'message', data: 'y', id: null })
  })

  it('ignora BOM no começo', () => {
    expect(parseSSE('﻿data: x\n\n')[0]?.data).toBe('x')
  })
})

describe('createSSEParser (stream em pedaços)', () => {
  it('chunk quebrado no meio de uma linha', () => {
    expect(collect(['da', 'ta: {"no', 'de":"x"}\n', '\n']).map((m) => m.data)).toEqual(['{"node":"x"}'])
  })

  it('chunk termina entre as duas quebras de linha', () => {
    expect(collect(['data: a\n', '\ndata: b\n', '\n']).map((m) => m.data)).toEqual(['a', 'b'])
  })

  it('\\r\\n partido entre dois chunks não gera linha vazia extra', () => {
    expect(collect(['data: a\r', '\n\r', '\ndata: b\r\n\r\n']).map((m) => m.data)).toEqual(['a', 'b'])
  })

  it('um byte por vez', () => {
    const text = 'event: e\ndata: ç1\r\ndata: 2\r\n\r\ndata: z\n\n'
    expect(collect([...text])).toEqual(parseSSE(text))
    expect(collect([...text]).map((m) => m.data)).toEqual(['ç1\n2', 'z'])
  })

  it('evento incompleto no fim do stream não é entregue', () => {
    expect(collect(['data: a\n\ndata: b\n'])).toHaveLength(1)
  })

  it('vários eventos e um pedaço no mesmo chunk', () => {
    const out: string[] = []
    const parser = createSSEParser((m) => out.push(m.data))
    parser.push('data: 1\n\ndata: 2\n\nda')
    expect(out).toEqual(['1', '2'])
    parser.push('ta: 3\n\n')
    expect(out).toEqual(['1', '2', '3'])
  })
})
