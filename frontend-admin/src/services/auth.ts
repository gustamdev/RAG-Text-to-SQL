import type { LoginInput, TokenResponse, User } from '../types/auth'
import { api, tokenStore } from './http'

export const authApi = {
  login: (input: LoginInput) => api<TokenResponse>('/auth/login', { method: 'POST', body: input }),
  me: () => api<User>('/auth/me'),
  logout: () => api<void>('/auth/logout', { method: 'POST' }),
}

/** Encerra a sessão: avisa o servidor (best-effort) e sempre limpa o token local. */
export async function endSession() {
  try {
    await authApi.logout()
  } catch {
    // servidor fora ou token já inválido: a sessão local cai do mesmo jeito
  }
  tokenStore.clear()
}
