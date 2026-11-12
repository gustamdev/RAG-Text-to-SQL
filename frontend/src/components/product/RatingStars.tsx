import { Star } from 'lucide-react'
import { rating as formatRating } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Nota 0–5 em estrelas + valor numérico. Sem avaliações vira texto neutro. */
export function RatingStars({
  value,
  count,
  className,
}: {
  value: number | null
  count?: number
  className?: string
}) {
  if (value === null) {
    return <span className={cn('text-xs text-muted-foreground', className)}>Sem avaliações</span>
  }
  const filled = Math.round(value)
  const label = `Nota ${formatRating(value)} de 5${count !== undefined ? `, ${count} avaliações` : ''}`
  return (
    <span role="img" aria-label={label} className={cn('inline-flex items-center gap-1.5 text-xs', className)}>
      <span className="inline-flex" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((n) => (
          <Star
            key={n}
            className={cn('size-3.5', n <= filled ? 'fill-foreground text-foreground' : 'text-border')}
            strokeWidth={1.5}
          />
        ))}
      </span>
      <span aria-hidden="true" className="font-semibold tabular-nums">
        {formatRating(value)}
      </span>
      {count !== undefined && (
        <span aria-hidden="true" className="text-muted-foreground tabular-nums">
          ({count.toLocaleString('pt-BR')})
        </span>
      )}
    </span>
  )
}
