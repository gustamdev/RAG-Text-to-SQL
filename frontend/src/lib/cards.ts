import { panOk } from '@/lib/product'
import type { CardInput } from '@/types/shop'

/** Campos do cartão como digitados (com máscara). O CVV só vive aqui até o envio. */
export interface CardValue { number: string; holder: string; exp: string; cvv: string }
export const EMPTY_CARD: CardValue = { number: '', holder: '', exp: '', cvv: '' }
export const MAX_CARDS = 3

export const maskPan = (raw: string) => raw.replace(/\D/g, '').slice(0, 16).replace(/(.{4})/g, '$1 ').trim()
export const maskExp = (raw: string) => { const d = raw.replace(/\D/g, '').slice(0, 4); return d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d }
export const cvvOk = (cvv: string) => /^\d{3,4}$/.test(cvv)
export const fmtExp = (c: { exp_month: number; exp_year: number }) => `${String(c.exp_month).padStart(2, '0')}/${String(c.exp_year).slice(-2)}`

/** Validade (mês/ano) já passou? O cartão vale até o fim do mês de validade. */
export const isExpired = (c: { exp_month: number; exp_year: number }, now = new Date()) =>
  c.exp_year * 12 + c.exp_month < now.getFullYear() * 12 + now.getMonth() + 1

export type CardField = 'num' | 'nm' | 'exp' | 'cvv'
/** Erro do formulário; `field` aponta o campo para aria-invalid (ausente = erro geral, ex.: servidor). */
export interface CardIssue { field?: CardField; message: string }

/** Primeiro problema do cartão digitado, ou undefined se estiver válido. */
export function cardIssue(c: CardValue, now = new Date()): CardIssue | undefined {
  const digits = c.number.replace(/\D/g, '')
  if (digits.length !== 16) return { field: 'num', message: 'Informe o número do cartão de teste (16 dígitos).' }
  if (!panOk(digits)) return { field: 'num', message: 'Número de cartão inválido. Confira os dígitos (ex.: 4242 4242 4242 0001).' }
  if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(c.exp)) return { field: 'exp', message: 'Validade no formato MM/AA.' }
  if (isExpired(toCardInput(c), now)) return { field: 'exp', message: 'Cartão vencido.' }
  if (!cvvOk(c.cvv) || !c.holder.trim()) return { field: c.holder.trim() ? 'cvv' : 'nm', message: 'Informe o nome e o CVV.' }
}

export const validateCard = (c: CardValue, now = new Date()): string | undefined => cardIssue(c, now)?.message

export function toCardInput(c: CardValue): CardInput {
  const [mm, yy] = c.exp.split('/')
  return { card_number: c.number.replace(/\D/g, ''), holder: c.holder.trim(), exp_month: Number(mm), exp_year: 2000 + Number(yy), cvv: c.cvv }
}
