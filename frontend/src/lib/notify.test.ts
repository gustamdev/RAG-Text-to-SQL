import { beforeEach, describe, expect, it, vi } from 'vitest'

const store = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
})

const calls: { kind: string; opts: { id: string; duration: number; action?: unknown } }[] = []
vi.mock('sonner', () => {
  const fn = (kind: string) => (_msg: unknown, opts: { id: string; duration: number }) => void calls.push({ kind, opts })
  return { toast: { success: fn('success'), info: fn('info'), warning: fn('warning'), error: fn('error') } }
})

import { ApiError } from '@/services/http'
import { durationFor, isTransient, notify, notifyApiError, toastId } from './notify'

beforeEach(() => {
  calls.length = 0
  store.clear()
})

describe('duração', () => {
  it('4 s sem ação, 8 s com ação, erro maior que sucesso', () => {
    expect(durationFor('success', false)).toBe(4000)
    expect(durationFor('success', true)).toBe(8000)
    expect(durationFor('error', false)).toBeGreaterThan(durationFor('success', false))
    expect(durationFor('error', true)).toBe(8000)
  })
})

describe('dedupe', () => {
  it('mesmo tipo e texto geram o mesmo id; id explícito vence', () => {
    expect(toastId('info', 'Item removido')).toBe(toastId('info', 'Item removido'))
    expect(toastId('info', 'Item removido')).not.toBe(toastId('error', 'Item removido'))
    expect(toastId('info', 'Item removido', 'cart-removed:p1')).toBe('cart-removed:p1')
  })

  it('o aviso repetido chega ao sonner com o mesmo id', () => {
    notify.success('Endereço salvo')
    notify.success('Endereço salvo')
    expect(calls[0]?.opts.id).toBe(calls[1]?.opts.id)
  })
})

describe('notifyApiError', () => {
  it('429, rede e 5xx usam ids fixos; retry só vira ação quando informado', () => {
    notifyApiError(new ApiError(429, 'x'))
    notifyApiError(new ApiError(0, 'x'))
    notifyApiError(new ApiError(503, 'x'), { retry: () => undefined })
    expect(calls.map((c) => c.opts.id)).toEqual(['rate-limit', 'server-error', 'server-error'])
    expect(calls[1]?.opts.action).toBeUndefined()
    expect(calls[2]?.opts.duration).toBe(8000)
  })

  it('401 sem token é silencioso (a sessão expirada já foi avisada); erro de domínio mostra a mensagem', () => {
    notifyApiError(new ApiError(401, 'Não autenticado'))
    expect(calls).toHaveLength(0)
    notifyApiError(new ApiError(409, 'Estoque insuficiente.'))
    expect(calls[0]?.kind).toBe('error')
  })

  it('isTransient não captura erro de campo', () => {
    expect(isTransient(new ApiError(422, 'x'))).toBe(false)
    expect(isTransient(new ApiError(0, 'x'))).toBe(true)
  })
})
