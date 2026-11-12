import { createContext } from 'react'
import type { User } from '../types/auth'

export interface AuthContextValue {
  user: User | null
  /** false enquanto a sessão salva (token) ainda está sendo validada no servidor. */
  ready: boolean
  /** Só administradores entram. Qualquer outro papel falha e não deixa token salvo. */
  login: (email: string, password: string) => Promise<User>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
