import { num, pct } from '@/lib/format'
import type { RatingBucket } from '@/types/product'

/** Distribuição de notas 1–5 em barras horizontais (HTML puro: leve e legível). Sempre mostra as 5 notas. */
export function RatingBars({ data }: { data: RatingBucket[] }) {
  const byScore = new Map(data.map((b) => [b.score, b.count]))
  const rows = [5, 4, 3, 2, 1].map((score) => ({ score, count: byScore.get(score) ?? 0 }))
  const total = rows.reduce((sum, r) => sum + r.count, 0)
  const max = Math.max(1, ...rows.map((r) => r.count))

  if (total === 0) {
    return <p className="py-8 text-sm text-muted-foreground">Nenhuma avaliação registrada.</p>
  }

  return (
    <ul className="space-y-2.5" aria-label="Distribuição das notas">
      {rows.map(({ score, count }) => (
        <li key={score} className="grid grid-cols-[2.25rem_1fr_6.5rem] items-center gap-3 text-xs">
          <span className="font-semibold tabular-nums">{score} ★</span>
          <div className="h-3 bg-muted" role="presentation">
            <div
              className={score <= 2 ? 'h-full bg-destructive' : 'h-full bg-foreground'}
              style={{ width: `${(count / max) * 100}%` }}
            />
          </div>
          <span className="text-right text-muted-foreground tabular-nums">
            {num(count)} · {pct((count / total) * 100, 0)}
          </span>
        </li>
      ))}
    </ul>
  )
}
