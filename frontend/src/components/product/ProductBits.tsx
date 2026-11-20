import { Minus, Plus } from 'lucide-react'
import { money, installment } from '@/lib/product'
import { notify } from '@/lib/notify'
import { cn } from '@/lib/utils'

export function PriceBlock({ cents, large }: { cents: number; large?: boolean }) {
  return (
    <div>
      <p className={cn('font-extrabold tabular-nums', large ? 'text-3xl' : 'text-lg')}>{money(cents)}</p>
      <p className="text-xs text-muted-foreground tabular-nums">ou 3x de {money(installment(cents))} sem juros (simulado)</p>
    </div>
  )
}

export function StockBadge({ stock }: { stock: number }) {
  if (stock < 1) return <span className="text-sm font-bold text-destructive">Esgotado</span>
  if (stock <= 5) return <span className="text-sm font-bold text-brand">Restam {stock}</span>
  return <span className="text-sm font-semibold text-success">Em estoque</span>
}

export function QuantityStepper({
  value,
  max,
  label,
  onChange,
  disabled,
}: {
  value: number
  max: number
  label: string
  onChange: (qty: number) => void
  disabled?: boolean
}) {
  const btn =
    'inline-flex size-11 items-center justify-center hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-40 aria-disabled:opacity-40 md:size-9'
  const limit = Math.min(10, max)
  const atLimit = value >= limit
  // aria-disabled (não disabled): o toque no limite explica por que não aumenta.
  const more = () =>
    atLimit
      ? notify.warning(max < 10 ? `Só há ${max} em estoque.` : 'Máximo de 10 unidades por item.', { id: 'qty-limit' })
      : onChange(value + 1)
  return (
    <div role="group" aria-label={`Quantidade de ${label}`} className="inline-flex items-center border border-input">
      <button type="button" className={btn} disabled={disabled || value <= 1} onClick={() => onChange(value - 1)}>
        <Minus className="size-4" aria-hidden="true" />
        <span className="sr-only">Diminuir quantidade de {label}</span>
      </button>
      <output aria-live="polite" className="min-w-8 text-center text-sm font-bold tabular-nums">
        {value}
      </output>
      <button type="button" className={btn} disabled={disabled} aria-disabled={atLimit || undefined} onClick={more}>
        <Plus className="size-4" aria-hidden="true" />
        <span className="sr-only">Aumentar quantidade de {label}</span>
      </button>
    </div>
  )
}
