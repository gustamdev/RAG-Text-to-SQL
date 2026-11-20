import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/services/http'
import { cartSignature, clearOpenOrder, isStale, keepKeyAfter, loadOpenOrder, saveOpenOrder } from './openOrder'

const store = new Map<string, string>()
vi.stubGlobal('sessionStorage', {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
})

describe('keepKeyAfter', () => {
  it('mantém a chave só em 504 e erro de rede', () => {
    expect(keepKeyAfter(new ApiError(504, 'x'))).toBe(true)
    expect(keepKeyAfter(new ApiError(0, 'x'))).toBe(true)
    expect(keepKeyAfter(new ApiError(409, 'x'))).toBe(false)
    expect(keepKeyAfter(new ApiError(422, 'x'))).toBe(false)
  })
})

describe('pedido aberto', () => {
  beforeEach(() => store.clear())
  const o = { id: 'o1', addressId: 'a1', shipping: 'standard' as const, cartSig: cartSignature([{ product_id: 'p', qty: 1 }]) }
  it('persiste e limpa', () => {
    saveOpenOrder(o)
    expect(loadOpenOrder()).toEqual(o)
    clearOpenOrder()
    expect(loadOpenOrder()).toBeNull()
  })
  it('detecta itens, endereço ou frete diferentes', () => {
    expect(isStale(o, 'a1', 'standard', o.cartSig)).toBe(false)
    expect(isStale(o, 'a1', 'standard', cartSignature([{ product_id: 'p', qty: 2 }]))).toBe(true)
    expect(isStale(o, 'a2', 'standard', o.cartSig)).toBe(true)
    expect(isStale(o, 'a1', 'economy', o.cartSig)).toBe(true)
  })
})
