const nf = new Intl.NumberFormat('pt-BR')
const nfCompact = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 })
const NO_VALUE = '—'

export function brl(value: number, opts: { cents?: boolean; compact?: boolean } = {}) {
  if (opts.compact) {
    return `R$ ${nfCompact.format(value)}`
  }
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: opts.cents ? 2 : 0,
    maximumFractionDigits: opts.cents ? 2 : 0,
  }).format(value)
}

export function dateBR(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })
}

/** Percentual a partir de um valor 0–100 ("12,3%"). `null` vira traço. */
export function pct(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_VALUE
  return `${value.toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`
}

/** Inteiro com separador de milhar; `compact` abrevia ("12 mil", "1,2 mi"). */
export function num(value: number, opts: { compact?: boolean } = {}) {
  return (opts.compact ? nfCompact : nf).format(value)
}

/** Nota média com uma casa ("4,3"). `null` vira traço. */
export function rating(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_VALUE
  return value.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

/** "2018-03" -> "mar/18". Entrada fora do formato volta como veio. */
export function monthLabel(month: string) {
  const match = /^(\d{4})-(\d{2})$/.exec(month)
  if (!match) return month
  const name = MONTHS[Number(match[2]) - 1]
  return name ? `${name}/${match[1]!.slice(2)}` : month
}

/** Medida física com unidade ("12 cm"). `null` vira traço. */
export function measure(value: number | null | undefined, unit: string) {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_VALUE
  return `${value.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${unit}`
}

/** Peso em gramas; a partir de 1 kg mostra em kg ("1,5 kg"). */
export function weight(grams: number | null | undefined) {
  if (grams === null || grams === undefined || Number.isNaN(grams)) return NO_VALUE
  return grams >= 1000 ? measure(grams / 1000, 'kg') : measure(grams, 'g')
}
