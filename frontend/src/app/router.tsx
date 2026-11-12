import type { ComponentType } from 'react'
import { Navigate, createBrowserRouter } from 'react-router'
import { BackofficeLayout } from '@/components/layout/BackofficeLayout'
import { PublicLayout } from '@/components/layout/PublicLayout'
import { RequireAdmin } from '@/components/RequireAdmin'
import { NotFound, RouteError } from './RouteError'

// Cada página vira um chunk próprio (o backoffice, os gráficos e o chat não pesam na vitrine). Com `lazy`
// do próprio router a navegação espera o chunk e mantém a página atual na tela, sem piscar um fallback.
const page = (load: () => Promise<{ default: ComponentType }>) => ({
  lazy: async () => ({ Component: (await load()).default }),
})

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, ...page(() => import('@/pages/Vitrine/HomePage')) },
      { path: 'produtos', ...page(() => import('@/pages/Vitrine/ProdutosPage')) },
      { path: 'produtos/:id', ...page(() => import('@/pages/Vitrine/ProdutoPage')) },
      { path: '*', element: <NotFound /> },
    ],
  },
  {
    path: 'backoffice/login',
    ...page(() => import('@/pages/Backoffice/LoginPage')),
    errorElement: <RouteError />,
  },
  {
    path: 'backoffice',
    element: <RequireAdmin />,
    errorElement: <RouteError />,
    children: [
      {
        element: <BackofficeLayout />,
        children: [
          { index: true, ...page(() => import('@/pages/Backoffice/VisaoGeralPage')) },
          { path: 'produtos', ...page(() => import('@/pages/Backoffice/ProdutosAdminPage')) },
          { path: 'produtos/:id', ...page(() => import('@/pages/Backoffice/ProdutoAdminPage')) },
          { path: 'categorias', ...page(() => import('@/pages/Backoffice/CategoriasPage')) },
          { path: 'assistente', ...page(() => import('@/pages/Assistente/AssistentePage')) },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
  // Endereço antigo do chat.
  { path: 'assistente', element: <Navigate to="/backoffice/assistente" replace /> },
])
