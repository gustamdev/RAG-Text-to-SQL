import type {
  Address,
  AddressInput,
  AuthSession,
  Cart,
  CancelReason,
  CardInput,
  CategoryOut,
  Customer,
  FreightResult,
  Order,
  OrderSummary,
  Page,
  PayInput,
  SavedCard,
  ProductCard,
  ProductDetail,
  ProductFilters,
  Suggestions,
  FreightCode,
} from '@/types/shop'
import { api } from './http'

const sig = (signal?: AbortSignal) => (signal ? { signal } : {})
const idem = (key: string) => ({ headers: { 'Idempotency-Key': key } })

export const catalogApi = {
  list: (filters: ProductFilters, signal?: AbortSignal) =>
    api<Page<ProductCard>>('/shop/products', {
      params: { ...filters, in_stock: filters.in_stock ? 'true' : undefined },
      ...sig(signal),
    }),
  get: (id: string, signal?: AbortSignal) => api<ProductDetail>(`/shop/products/${encodeURIComponent(id)}`, sig(signal)),
  categories: (signal?: AbortSignal) => api<CategoryOut[]>('/shop/products/categories', sig(signal)),
  suggest: (q: string, signal?: AbortSignal) => api<Suggestions>('/shop/products/suggest', { params: { q }, ...sig(signal) }),
  batch: (ids: string[], signal?: AbortSignal) =>
    api<{ items: ProductCard[] }>('/shop/products/batch', { method: 'POST', body: { ids }, ...sig(signal) }),
  freight: (id: string, zip: string) =>
    api<FreightResult>(`/shop/products/${encodeURIComponent(id)}/freight`, { params: { zip } }),
}

export const authApi = {
  signup: (body: { nickname?: string; email: string; password: string; terms_version: string }) =>
    api<{ detail: string }>('/shop/auth/signup', { method: 'POST', body: { ...body, accept_terms: true, accept_adult: true } }),
  verifySignup: (email: string, code: string) =>
    api<AuthSession>('/shop/auth/verify-otp', { method: 'POST', body: { email, code } }),
  login: (email: string, password: string) =>
    api<{ mfa_required: boolean; masked_email: string }>('/shop/auth/login', { method: 'POST', body: { email, password } }),
  verifyLogin: (email: string, code: string) =>
    api<AuthSession>('/shop/auth/login/verify-otp', { method: 'POST', body: { email, code } }),
  resend: (email: string, purpose: 'signup' | 'login') =>
    api<{ detail: string }>('/shop/auth/resend-otp', { method: 'POST', body: { email, purpose } }),
  forgotPassword: (email: string) =>
    api<{ masked_email: string; message: string }>('/shop/auth/forgot-password', { method: 'POST', body: { email } }),
  resetPassword: (email: string, code: string, new_password: string) =>
    api<{ ok: true }>('/shop/auth/reset-password', { method: 'POST', body: { email, code, new_password } }),
  // skipAuthReset: sair com token já revogado (troca de senha, conta excluída) não é "sessão expirada".
  logout: () => api<void>('/shop/auth/logout', { method: 'POST', skipAuthReset: true }),
  me: () => api<Customer>('/shop/auth/me'),
}

export const cartApi = {
  get: () => api<Cart>('/shop/cart'),
  add: (product_id: string, qty: number) => api<Cart>('/shop/cart/items', { method: 'POST', body: { product_id, qty } }),
  patch: (product_id: string, body: { qty?: number; ack?: boolean }) =>
    api<Cart>(`/shop/cart/items/${encodeURIComponent(product_id)}`, { method: 'PATCH', body }),
  remove: (product_id: string) => api<Cart>(`/shop/cart/items/${encodeURIComponent(product_id)}`, { method: 'DELETE' }),
  merge: (items: { product_id: string; qty: number }[]) => api<Cart>('/shop/cart/merge', { method: 'POST', body: { items } }),
  freight: (body: { zip: string } | { address_id: string }) =>
    api<FreightResult>('/shop/cart/freight', { method: 'POST', body }),
}

export const checkoutApi = {
  create: (address_id: string, shipping_option: FreightCode, key: string) =>
    api<Order>('/shop/checkout', { method: 'POST', body: { address_id, shipping_option }, ...idem(key) }),
  pay: (
    orderId: string,
    card: PayInput,
    key: string,
  ) =>
    api<{ order: Order; payment: { status: 'approved' | 'refused'; brand: string; last4: string } }>(
      `/shop/checkout/${orderId}/pay`,
      { method: 'POST', body: card, ...idem(key) },
    ),
}

export const accountApi = {
  addresses: () => api<Address[]>('/shop/account/addresses'),
  addAddress: (body: AddressInput) => api<Address>('/shop/account/addresses', { method: 'POST', body }),
  setDefaultAddress: (id: string) =>
    api<Address>(`/shop/account/addresses/${id}`, { method: 'PATCH', body: { is_default: true } }),
  exportData: () => api<unknown>('/shop/account/export'),
  // skipAuthReset: 401 aqui é "Senha incorreta.", não sessão vencida.
  changePassword: (body: { current_password: string; new_password: string; code?: string }) =>
    api<void>('/shop/account/password', { method: 'PATCH', body, skipAuthReset: true }),
  updateProfile: (body: { nickname?: string; phone?: string | null }) =>
    api<{ id: string; nickname: string | null; email: string; phone: string | null }>('/shop/account', { method: 'PATCH', body }),
  deleteAccount: (body: { password: string; confirm: 'EXCLUIR' }) =>
    api<void>('/shop/account', { method: 'DELETE', body, skipAuthReset: true }),
  removeAddress: (id: string) => api<void>(`/shop/account/addresses/${id}`, { method: 'DELETE' }),
  cards: () => api<SavedCard[]>('/shop/account/cards'),
  addCard: (body: CardInput) => api<SavedCard>('/shop/account/cards', { method: 'POST', body }),
  removeCard: (id: string) => api<void>(`/shop/account/cards/${id}`, { method: 'DELETE' }),
  orders: (page: number) => api<Page<OrderSummary>>('/shop/orders', { params: { page, page_size: 20 } }),
  order: (id: string) => api<Order>(`/shop/orders/${id}`),
  cancel: (id: string, reason?: CancelReason) => api<Order>(`/shop/orders/${id}/cancel`, { method: 'POST', ...(reason && { body: { reason } }) }),
}

export const zipApi = {
  lookup: (cep8: string, signal?: AbortSignal) => api<{ zip: string; street: string | null; district: string | null; city: string; state: string; lat: number | null; lng: number | null; source: string }>(`/shop/zip/${cep8}`, sig(signal)),
}

export const legalApi = {
  get: () => api<{ version: string; terms: string; privacy: string }>('/shop/legal'),
}
