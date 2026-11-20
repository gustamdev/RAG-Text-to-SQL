import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { guestCart } from '@/lib/guestCart'
import { clearOpenOrder } from '@/lib/openOrder'
import { clearZip } from '@/hooks/useZip'
import { notify } from '@/lib/notify'
import { UNAUTHORIZED_EVENT, clearToken, getToken, setToken } from '@/lib/session'
import { ApiError } from '@/services/http'
import { authApi } from '@/services/shop'
import type { AuthSession, Customer } from '@/types/shop'
import { router } from './router'
import { syncCartOnLogin } from './syncCart'
import { CustomerContext } from './customer-context'

export function CustomerAuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [loading, setLoading] = useState(() => getToken() !== null)

  useEffect(() => {
    if (!getToken()) return
    let alive = true
    authApi
      .me()
      .then((c) => alive && setCustomer(c))
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 401) clearToken()
      })
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const onExpired = () => {
      setCustomer(null)
      qc.removeQueries({ queryKey: ['cart'] })
      notify.warning('Sua sessão expirou. Entre novamente.', {
        id: 'session-expired',
        action: {
          label: 'Entrar',
          onClick: () => {
            const { pathname, search } = router.state.location
            void router.navigate(`/entrar?redirect=${encodeURIComponent(pathname + search)}`)
          },
        },
      })
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onExpired)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onExpired)
  }, [qc])

  const signIn = useCallback(
    async (session: AuthSession) => {
      setToken(session.access_token)
      await syncCartOnLogin(qc, () => setCustomer(session.customer))
    },
    [qc],
  )

  const signOut = useCallback(async (quiet = false) => {
    try {
      await authApi.logout()
    } catch {
      /* token já inválido: segue limpando */
    }
    clearToken()
    guestCart.clear()
    clearZip()
    clearOpenOrder()
    setCustomer(null)
    qc.removeQueries({ queryKey: ['cart'] })
    qc.removeQueries({ queryKey: ['account'] })
    if (!quiet) notify.info('Você saiu da conta.', { id: 'signed-out' })
  }, [qc])

  const updateCustomer = useCallback((patch: Partial<Customer>) => setCustomer((c) => (c ? { ...c, ...patch } : c)), [])
  const value = useMemo(() => ({ customer, loading, signIn, signOut, updateCustomer }), [customer, loading, signIn, signOut, updateCustomer])
  return <CustomerContext value={value}>{children}</CustomerContext>
}
