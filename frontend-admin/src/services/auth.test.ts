import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { endSession } from './auth'
import { tokenStore } from './http'

beforeEach(() => vi.stubGlobal('window', { location: { origin: 'http://localhost' } }))
afterEach(() => vi.unstubAllGlobals())

describe('endSession', () => {
  it('chama POST /auth/logout com o token e limpa', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    tokenStore.set('tok')
    await endSession()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/auth/logout')
    expect(init.method).toBe('POST')
    expect(tokenStore.get()).toBeNull()
  })

  it('limpa o token mesmo se a API falhar', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    tokenStore.set('tok')
    await expect(endSession()).resolves.toBeUndefined()
    expect(tokenStore.get()).toBeNull()
  })
})
