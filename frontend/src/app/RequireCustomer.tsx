import { Navigate, Outlet, useLocation } from 'react-router'
import { LoadingBlock } from '@/components/StateViews'
import { useCustomer } from './customer-context'

export function RequireCustomer() {
  const { customer, loading } = useCustomer()
  const { pathname, search } = useLocation()
  if (loading) return <LoadingBlock label="Verificando sessão…" />
  if (!customer) return <Navigate to={`/entrar?redirect=${encodeURIComponent(pathname + search)}`} replace />
  return <Outlet />
}
