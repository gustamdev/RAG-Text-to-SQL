import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi, endSession } from '../services/auth'
import { ApiError, setUnauthorizedHandler, tokenStore } from '../services/http'
import type { User } from '../types/auth'
import { AuthContext, type AuthContextValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(() => tokenStore.get() === null)

  const clearLocal = useCallback(() => {
    tokenStore.clear()
    setUser(null)
    queryClient.clear() // nada de dados do admin anterior na tela do próximo
  }, [queryClient])

  // Saída pedida pelo usuário: avisa a API antes de limpar o token.
  const logout = useCallback(async () => {
    await endSession()
    clearLocal()
  }, [clearLocal])

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
    // Só limpeza local: chamar a API aqui geraria laço de 401.
    setUnauthorizedHandler(clearLocal)
    return () => setUnauthorizedHandler(null)
  }, [clearLocal])

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
