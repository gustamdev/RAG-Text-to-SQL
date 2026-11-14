// Hooks de dados da vitrine pública (TanStack Query). Chaves incluem os filtros.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { productsApi } from '../services/products'
import type { ProductFilters } from '../types/product'

export const useProducts = (filters: ProductFilters) =>
  useQuery({
    queryKey: ['products', filters],
    queryFn: ({ signal }) => productsApi.list(filters, signal),
    placeholderData: keepPreviousData,
  })

export const useProduct = (id: string | undefined) =>
  useQuery({
    queryKey: ['product', id],
    queryFn: ({ signal }) => productsApi.get(id!, signal),
    enabled: !!id,
    retry: false,
  })

export const useCategories = () =>
  useQuery({
    queryKey: ['categories'],
    queryFn: ({ signal }) => productsApi.categories(signal),
    staleTime: 5 * 60_000,
  })
