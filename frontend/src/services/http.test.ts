import { beforeEach, expect, it, vi } from 'vitest'

const store = new Map<string, string>([['olist.shop.token', 't']])
const events: string[] = []
vi.stubGlobal('localStorage', {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
})
vi.stubGlobal('window', { location: { origin: 'http://x' }, dispatchEvent: (e: Event) => events.push(e.type) })

import { api } from './http'

beforeEach(() => {
  store.set('olist.shop.token', 't')
  events.length = 0
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Senha incorreta.' }), { status: 401 })))
})

it('401 comum limpa o token e avisa', async () => {
  await expect(api('/shop/cart')).rejects.toThrow()
  expect(store.has('olist.shop.token')).toBe(false)
  expect(events).toEqual(['shop:unauthorized'])
})

it('401 de reautenticação (skipAuthReset) mantém o token', async () => {
  await expect(api('/shop/account', { method: 'DELETE', skipAuthReset: true })).rejects.toThrow('Senha incorreta.')
  expect(store.has('olist.shop.token')).toBe(true)
  expect(events).toEqual([])
})
