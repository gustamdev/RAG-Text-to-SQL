// Hooks de dados do backoffice. Chaves incluem o id do admin: trocar de conta nunca mostra dados da anterior.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { backofficeApi } from '../services/backoffice'
import type { AdminProductFilters } from '../types/product'
import { useAuth } from './useAuth'

function useUserId() {
  const { user } = useAuth()
  return user?.id ?? null
}

export function useOverview() {
  const uid = useUserId()
  return useQuery({
    queryKey: ['bo', uid, 'overview'],
    queryFn: ({ signal }) => backofficeApi.overview(signal),
    enabled: !!uid,
  })
}

export function useAdminProducts(filters: AdminProductFilters) {
  const uid = useUserId()
  return useQuery({
    queryKey: ['bo', uid, 'products', filters],
    queryFn: ({ signal }) => backofficeApi.products(filters, signal),
    enabled: !!uid,
    placeholderData: keepPreviousData,
  })
}

export function useAdminProduct(id: string | undefined) {
  const uid = useUserId()
  return useQuery({
    queryKey: ['bo', uid, 'product', id],
    queryFn: ({ signal }) => backofficeApi.product(id!, signal),
    enabled: !!uid && !!id,
    retry: false,
  })
}

export function useAdminCategories() {
  const uid = useUserId()
  return useQuery({
    queryKey: ['bo', uid, 'categories'],
    queryFn: ({ signal }) => backofficeApi.categories(signal),
    enabled: !!uid,
  })
}
