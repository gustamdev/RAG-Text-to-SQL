import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuth } from '@/hooks/useAuth'
import { LoadingBlock } from './StateViews'

/**
 * Guarda de rota do backoffice (use como `element` de uma rota-pai com filhos). Sem sessão de
 * administrador, manda para o login guardando o destino em ?redirect=. A checagem real é do servidor.
 */
export function RequireAdmin() {
  const { user, ready } = useAuth()
  const location = useLocation()

  if (!ready) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 md:px-8">
        <LoadingBlock />
      </div>
    )
  }

  if (!user || user.role !== 'admin') {
    const redirect = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?redirect=${redirect}`} replace />
  }

  return <Outlet />
}
