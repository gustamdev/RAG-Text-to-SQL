import type { CancelReason } from '@/types/shop'
export const productHref = (id: string) => `/produtos/${encodeURIComponent(id)}`
export const categoryHref = (category: string) => `/c/${encodeURIComponent(category)}`
export const searchHref = (q: string) => `/busca?q=${encodeURIComponent(q)}`

/** Parcelamento simulado em 3x sem juros (só exibição). */
export const installment = (cents: number) => Math.ceil(cents / 3)

/** Centavos -> "R$ 89,90". */
export function money(cents: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(cents / 100)
}

export const normalizeZip = (value: string) => value.replace(/[^0-9]/g, '').slice(0, 8)
export const maskZip = (value: string) => {
  const z = normalizeZip(value)
  return z.length > 5 ? `${z.slice(0, 5)}-${z.slice(5)}` : z
}
/** "sao paulo" -> "Sao Paulo" (o backend devolve minúsculo, sem acento). */
export const titleCase = (value: string) => value.toLowerCase().replace(/(^|\s)(\p{L})/gu, (_, sp: string, c: string) => sp + c.toUpperCase())
export const isZip = (value: string) => normalizeZip(value).length === 8

/** Chave de idempotência (8-64 chars [A-Za-z0-9_-]); uma por operação. */
export const newIdempotencyKey = () => `k${crypto.randomUUID().replace(/-/g, '')}`

export const ORDER_STATE_LABEL: Record<string, string> = {
  created: 'Aguardando pagamento',
  paid: 'Pago',
  refused: 'Pagamento recusado',
  shipped: 'Enviado',
  delivered: 'Entregue',
  canceled: 'Cancelado',
}

export const CANCEL_REASON_LABEL: Record<CancelReason, string> = {
  changed_mind: 'Mudei de ideia',
  found_cheaper: 'Encontrei mais barato',
  wrong_item: 'Produto errado',
  delivery_too_long: 'Entrega demorada',
  other: 'Outro',
}

/** Estados em que o cliente ainda pode cancelar (shipped/delivered dão 409). */
export const isCancelable = (state: string) => state === 'created' || state === 'refused' || state === 'paid'

/** Nomes de categoria vêm em snake_case do backend ("cama_mesa_banho"): formata para exibição. */
export function categoryLabel(category: string | null | undefined): string {
  const text = (category ?? '').replace(/_+/g, ' ').trim()
  if (!text || text === 'sem categoria') return 'Sem categoria'
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Cartões de teste do gateway fake: valem sem Luhn (iguais a TEST_CARDS no backend). */
const TEST_PANS = new Set(['4242424242420001', '4242424242420002', '4242424242420003'])

/** Mesma regra do gateway: número digitado errado é barrado antes de gastar uma tentativa de pagamento. */
export function panOk(pan: string): boolean {
  if (TEST_PANS.has(pan)) return true
  let total = 0
  for (let i = 0; i < pan.length; i++) {
    let d = Number(pan[pan.length - 1 - i])
    if (i % 2) d = d > 4 ? d * 2 - 9 : d * 2
    total += d
  }
  return pan.length > 0 && total % 10 === 0
}
