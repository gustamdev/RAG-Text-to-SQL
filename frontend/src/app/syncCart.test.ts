import { QueryClient } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'

const store = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
})
const merged = { items: [], item_count: 3, subtotal_cents: 0, blocked: false }
vi.mock('@/services/shop', () => ({ cartApi: { merge: vi.fn(async () => merged), get: vi.fn(async () => merged) } }))

import { syncCartOnLogin } from './syncCart'

beforeEach(() => store.clear())

it('grava o carrinho mesclado antes de liberar o login', async () => {
  store.set('olist.shop.guestcart', JSON.stringify([{ product_id: 'p', qty: 3 }]))
  const qc = new QueryClient()
  let atReady: unknown
  await syncCartOnLogin(qc, () => (atReady = qc.getQueryData(['cart'])))
  expect(atReady).toEqual(merged)
  expect(store.get('olist.shop.guestcart')).toBe('[]')
})
