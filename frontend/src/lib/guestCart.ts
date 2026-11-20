// Carrinho de convidado em localStorage: só product_id e qty; preço e estoque vêm de /shop/products/batch.
import { useSyncExternalStore } from 'react'

export interface GuestItem {
  product_id: string
  qty: number
}

const KEY = 'olist.shop.guestcart'
const MAX_QTY = 10
const MAX_ITEMS = 50
const listeners = new Set<() => void>()
let cache: { raw: string | null; items: GuestItem[] } = { raw: null, items: [] }

function read(): GuestItem[] {
  const raw = localStorage.getItem(KEY)
  if (raw === cache.raw) return cache.items
  let items: GuestItem[] = []
  try {
    const parsed: unknown = JSON.parse(raw ?? '[]')
    if (Array.isArray(parsed)) {
      items = parsed.filter(
        (i): i is GuestItem =>
          typeof i?.product_id === 'string' && Number.isInteger(i?.qty) && i.qty >= 1 && i.qty <= MAX_QTY,
      )
    }
  } catch {
    /* json inválido: carrinho vazio */
  }
  cache = { raw, items }
  return items
}

function write(items: GuestItem[]) {
  localStorage.setItem(KEY, JSON.stringify(items.slice(0, MAX_ITEMS)))
  listeners.forEach((fn) => fn())
}

export const guestCart = {
  get: read,
  add(product_id: string, qty: number) {
    const items = read()
    const found = items.find((i) => i.product_id === product_id)
    if (found) write(items.map((i) => (i === found ? { ...i, qty: Math.min(MAX_QTY, i.qty + qty) } : i)))
    else write([...items, { product_id, qty: Math.min(MAX_QTY, qty) }])
  },
  setQty(product_id: string, qty: number) {
    write(read().map((i) => (i.product_id === product_id ? { ...i, qty: Math.min(MAX_QTY, Math.max(1, qty)) } : i)))
  },
  remove: (product_id: string) => write(read().filter((i) => i.product_id !== product_id)),
  clear: () => write([]),
}

export function useGuestItems(): GuestItem[] {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    read,
  )
}
