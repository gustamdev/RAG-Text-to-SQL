import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { Toaster } from '@/components/ui/sonner'
import { CustomerAuthProvider } from './app/CustomerAuthProvider'
import { router } from './app/router'
import { ApiError } from './services/http'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      // Erro 4xx (não encontrado, sem permissão, sessão) não melhora com nova tentativa.
      retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <CustomerAuthProvider>
        <RouterProvider router={router} />
      </CustomerAuthProvider>
      <Toaster />
    </QueryClientProvider>
  </StrictMode>,
)
