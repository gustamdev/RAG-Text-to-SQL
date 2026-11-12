import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi } from '../services/auth'
import { ApiError, setUnauthorizedHandler, tokenStore } from '../services/http'
import type { User } from '../types/auth'
import { AuthContext, type AuthContextValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(() => tokenStore.get() === null)

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
    queryClient.clear() // nada de dados do admin anterior na tela do próximo
  }, [queryClient])

  // Restaura a sessão salva. Token inválido/expirado, ou de quem não é admin, é descartado em silêncio.
  useEffect(() => {
    if (tokenStore.get() === null) return
    let cancelled = false
    authApi
      .me()
      .then((me) => {
        if (cancelled) return
        if (me.role === 'admin') setUser(me)
        else tokenStore.clear()
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 401) tokenStore.clear()
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // O servidor recusou o token numa chamada qualquer (expirou): encerra a sessão local.
  useEffect(() => {
    setUnauthorizedHandler(logout)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  const login = useCallback<AuthContextValue['login']>(
    async (email, password) => {
      const res = await authApi.login({ email, password })
      if (res.user.role !== 'admin') {
        tokenStore.clear()
        throw new Error('Esta conta não tem acesso ao backoffice.')
      }
      queryClient.clear()
      tokenStore.set(res.access_token)
      setUser(res.user)
      return res.user
    },
    [queryClient],
  )

  const value = useMemo(() => ({ user, ready, login, logout }), [user, ready, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
