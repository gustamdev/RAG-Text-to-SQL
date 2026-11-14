import type { ComponentType } from 'react'
import { createBrowserRouter } from 'react-router'
import { PublicLayout } from '@/components/layout/PublicLayout'
import { NotFound, RouteError } from './RouteError'

// Cada página vira um chunk próprio (cada tela carrega só o que usa). Com `lazy`
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
])
