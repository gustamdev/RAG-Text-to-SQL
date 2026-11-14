import type { CategoryOut, Page, ProductDetail, ProductFilters, ProductSummary } from '../types/product'
import { api } from './http'

export const productsApi = {
  list: (filters: ProductFilters, signal?: AbortSignal) =>
    api<Page<ProductSummary>>('/products', { params: { ...filters }, ...(signal ? { signal } : {}) }),
  get: (id: string, signal?: AbortSignal) =>
    api<ProductDetail>(`/products/${encodeURIComponent(id)}`, signal ? { signal } : {}),
  categories: (signal?: AbortSignal) => api<CategoryOut[]>('/categories', signal ? { signal } : {}),
}
