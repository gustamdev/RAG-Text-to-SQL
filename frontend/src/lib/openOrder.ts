// Pedido aberto (created/refused) do checkout, guardado em sessionStorage para sobreviver a reload.
import { ApiError } from '@/services/http'
import type { FreightCode } from '@/types/shop'

export interface OpenOrder {
  id: string
  addressId: string
  shipping: FreightCode
  /** Assinatura dos itens do carrinho no momento da criação. */
  cartSig: string
}

const KEY = 'olist.shop.openorder'

export const cartSignature = (items: { product_id: string; qty: number }[]): string =>
  items.map((i) => `${i.product_id}:${i.qty}`).sort().join('|')

export function loadOpenOrder(): OpenOrder | null {
  try {
    const o: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? 'null')
    const v = o as Partial<OpenOrder> | null
    return v && typeof v.id === 'string' && typeof v.addressId === 'string' && typeof v.shipping === 'string' && typeof v.cartSig === 'string'
      ? (v as OpenOrder)
      : null
  } catch {
    return null
  }
}
export const saveOpenOrder = (o: OpenOrder) => sessionStorage.setItem(KEY, JSON.stringify(o))
export const clearOpenOrder = () => sessionStorage.removeItem(KEY)

/** Pedido aberto não vale mais para o que o cliente escolheu agora. */
export const isStale = (o: OpenOrder, addressId: string, shipping: FreightCode, cartSig: string): boolean =>
  o.addressId !== addressId || o.shipping !== shipping || o.cartSig !== cartSig

/** Idempotency-Key só pode ser reaproveitada em 504/rede; qualquer 4xx tem resposta persistida e exige chave nova. */
export const keepKeyAfter = (e: unknown): boolean => !(e instanceof ApiError && e.status >= 400 && e.status < 500)
