import type {
  AdminCategoryRow,
  AdminProductDetail,
  AdminProductFilters,
  AdminProductRow,
  Overview,
  Page,
} from '../types/product'
import { api } from './http'

export const backofficeApi = {
  overview: (signal?: AbortSignal) => api<Overview>('/admin/overview', signal ? { signal } : {}),
  products: (filters: AdminProductFilters, signal?: AbortSignal) =>
    api<Page<AdminProductRow>>('/admin/products', { params: { ...filters }, ...(signal ? { signal } : {}) }),
  product: (id: string, signal?: AbortSignal) =>
    api<AdminProductDetail>(`/admin/products/${encodeURIComponent(id)}`, signal ? { signal } : {}),
  categories: (signal?: AbortSignal) => api<AdminCategoryRow[]>('/admin/categories', signal ? { signal } : {}),
}
