import type { ComponentType } from 'react'
import { createBrowserRouter } from 'react-router'
import { BackofficeLayout } from '@/components/layout/BackofficeLayout'
import { RequireAdmin } from '@/components/RequireAdmin'
import { NotFound, RouteError } from './RouteError'

// Cada página vira um chunk próprio (gráficos e chat só carregam quando a tela é aberta).
const page = (load: () => Promise<{ default: ComponentType }>) => ({
  lazy: async () => ({ Component: (await load()).default }),
})

export const router = createBrowserRouter([
  {
    path: 'login',
    ...page(() => import('@/pages/Backoffice/LoginPage')),
    errorElement: <RouteError />,
  },
  {
    path: '/',
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
])
