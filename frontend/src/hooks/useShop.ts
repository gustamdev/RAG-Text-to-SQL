// Hooks de dados da loja (TanStack Query) e carrinho unificado (convidado local / servidor).
import { useEffect } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCustomer } from '@/app/customer-context'
import { guestCart, useGuestItems } from '@/lib/guestCart'
import { accountApi, cartApi, catalogApi } from '@/services/shop'
import type { Cart, CartLine, ProductFilters } from '@/types/shop'

export const useProducts = (filters: ProductFilters, enabled = true) =>
  useQuery({
    queryKey: ['products', filters],
    queryFn: ({ signal }) => catalogApi.list(filters, signal),
    placeholderData: keepPreviousData,
    enabled,
  })

export const useProduct = (id: string | undefined) =>
  useQuery({
    queryKey: ['product', id],
    queryFn: ({ signal }) => catalogApi.get(id!, signal),
    enabled: !!id,
    retry: false,
  })

export const useCategories = () =>
  useQuery({ queryKey: ['categories'], queryFn: ({ signal }) => catalogApi.categories(signal), staleTime: 5 * 60_000 })

export const useAddresses = () => useQuery({ queryKey: ['account', 'addresses'], queryFn: accountApi.addresses })
export const useCards = () => useQuery({ queryKey: ['account', 'cards'], queryFn: accountApi.cards })

const EMPTY: Cart = { items: [], item_count: 0, subtotal_cents: 0, blocked: false }

/** Carrinho do servidor (logado) ou montado do localStorage + /batch (convidado). */
export function useCart() {
  const { customer } = useCustomer()
  const guest = useGuestItems()
  const ids = guest.map((i) => i.product_id)

  const server = useQuery({ queryKey: ['cart'], queryFn: cartApi.get, enabled: !!customer })
  const batch = useQuery({
    queryKey: ['guest-cart', ids.join(',')],
    queryFn: ({ signal }) => catalogApi.batch(ids, signal),
    enabled: !customer && ids.length > 0,
    placeholderData: keepPreviousData,
  })

  // Ids que o /batch não devolveu (produto removido) saem do localStorage.
  useEffect(() => {
    if (customer || !batch.data || batch.isPlaceholderData) return
    const alive = new Set(batch.data.items.map((p) => p.product_id))
    ids.filter((id) => !alive.has(id)).forEach(guestCart.remove)
  }, [customer, batch.data, batch.isPlaceholderData, ids])

  if (customer) {
    return { cart: server.data ?? EMPTY, isLoading: server.isLoading, isError: server.isError, refetch: server.refetch }
  }
  const byId = new Map((batch.data?.items ?? []).map((p) => [p.product_id, p]))
  const items: CartLine[] = guest.flatMap((g) => {
    const p = byId.get(g.product_id)
    if (!p) return []
    const qty = Math.min(g.qty, p.stock)
    const out = p.stock < 1
    return [
      {
        product_id: p.product_id,
        title: p.title,
        category: p.category,
        unit_price_cents: p.price_cents,
        qty: out ? g.qty : qty,
        line_total_cents: p.price_cents * (out ? g.qty : qty),
        stock: p.stock,
        warning: out ? 'out_of_stock' : qty < g.qty ? 'stock_reduced' : null,
      } satisfies CartLine,
    ]
  })
  const cart: Cart =
    ids.length === 0
      ? EMPTY
      : {
          items,
          item_count: items.reduce((n, l) => n + l.qty, 0),
          subtotal_cents: items.reduce((n, l) => n + (l.warning === 'out_of_stock' ? 0 : l.line_total_cents), 0),
          blocked: items.some((l) => l.warning),
        }
  return { cart, isLoading: ids.length > 0 && batch.isLoading, isError: batch.isError, refetch: batch.refetch }
}

export function useCartActions() {
  const { customer } = useCustomer()
  const qc = useQueryClient()
  const setCart = (cart: Cart) => qc.setQueryData(['cart'], cart)

  const add = useMutation({
    mutationFn: async ({ id, qty }: { id: string; qty: number }) => {
      if (customer) return setCart(await cartApi.add(id, qty))
      guestCart.add(id, qty)
    },
  })
  const setQty = useMutation({
    mutationFn: async ({ id, qty }: { id: string; qty: number }) => {
      if (customer) return setCart(await cartApi.patch(id, { qty }))
      guestCart.setQty(id, qty)
    },
  })
  const ack = useMutation({
    mutationFn: async (id: string) => {
      // Convidado: o ajuste de quantidade já vale; só persiste a quantidade vista.
      if (customer) return setCart(await cartApi.patch(id, { ack: true }))
      const line = guestCart.get().find((i) => i.product_id === id)
      const batch = await catalogApi.batch([id])
      const stock = batch.items[0]?.stock ?? 0
      if (line && stock > 0) guestCart.setQty(id, Math.min(line.qty, stock))
    },
  })
  const remove = useMutation({
    mutationFn: async (id: string) => {
      if (customer) return setCart(await cartApi.remove(id))
      guestCart.remove(id)
    },
  })
  return { add, setQty, ack, remove }
}
