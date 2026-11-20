import type { ComponentType } from 'react'
import { createBrowserRouter } from 'react-router'
import { ShopLayout } from '@/components/layout/ShopLayout'
import { NotFound, RouteError } from './RouteError'
import { RequireCustomer } from './RequireCustomer'

// Cada página vira um chunk próprio; o `lazy` do router mantém a página atual na tela até o chunk chegar.
const page = (load: () => Promise<{ default: ComponentType }>) => ({
  lazy: async () => ({ Component: (await load()).default }),
})
const named = <K extends string>(load: () => Promise<Record<K, ComponentType>>, key: K) => ({
  lazy: async () => ({ Component: (await load())[key] }),
})
const auth = () => import('@/pages/Shop/AuthPages')
const account = () => import('@/pages/Shop/AccountPages')

export const router = createBrowserRouter([
  {
    element: <ShopLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, ...page(() => import('@/pages/Shop/HomePage')) },
      { path: 'c/:categoria', ...page(() => import('@/pages/Shop/ListingPage')) },
      { path: 'busca', ...page(() => import('@/pages/Shop/ListingPage')) },
      { path: 'produtos/:id', ...page(() => import('@/pages/Shop/ProductPage')) },
      { path: 'carrinho', ...page(() => import('@/pages/Shop/CartPage')) },
      { path: 'categorias', ...page(() => import('@/pages/Shop/CategoriesPage')) },
      { path: 'termos', ...page(() => import('@/pages/Shop/LegalPage')) },
      { path: 'privacidade', ...page(() => import('@/pages/Shop/LegalPage')) },
      { path: 'sobre', ...page(() => import('@/pages/Shop/AboutPage')) },
      { path: 'entrar', ...named(auth, 'LoginPage') },
      { path: 'entrar/codigo', lazy: async () => { const { CodePage } = await auth(); return { Component: () => <CodePage mode="login" /> } } },
      { path: 'esqueci-senha', ...named(auth, 'ForgotPasswordPage') },
      { path: 'redefinir-senha', ...named(auth, 'ResetPasswordPage') },
      { path: 'cadastro', ...named(auth, 'SignupPage') },
      { path: 'cadastro/codigo', lazy: async () => { const { CodePage } = await auth(); return { Component: () => <CodePage mode="signup" /> } } },
      {
        element: <RequireCustomer />,
        children: [
          { path: 'checkout', ...page(() => import('@/pages/Shop/CheckoutPage')) },
          { path: 'pedido/:id/confirmacao', lazy: async () => { const { OrderView } = await account(); return { Component: () => <OrderView confirmation /> } } },
          {
            path: 'conta',
            ...named(account, 'AccountLayout'),
            children: [
              { index: true, ...named(account, 'AccountHome') },
              { path: 'pedidos', ...named(account, 'OrdersPage') },
              { path: 'enderecos', ...named(account, 'AddressesPage') },
              { path: 'pagamentos', ...named(account, 'PaymentsPage') },
              { path: 'seguranca', ...named(account, 'SecurityPage') },
              { path: 'pedidos/:id', lazy: async () => { const { OrderView } = await account(); return { Component: () => <OrderView /> } } },
            ],
          },
        ],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
])
