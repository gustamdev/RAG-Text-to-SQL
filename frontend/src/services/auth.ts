import type { LoginInput, TokenResponse, User } from '../types/auth'
import { api } from './http'

export const authApi = {
  login: (input: LoginInput) => api<TokenResponse>('/auth/login', { method: 'POST', body: input }),
  me: () => api<User>('/auth/me'),
}
