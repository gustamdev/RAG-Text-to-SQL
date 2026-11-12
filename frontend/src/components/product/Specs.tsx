import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Lista de pares rótulo/valor (atributos do produto). */
export function Specs({ items, className }: { items: ReadonlyArray<readonly [string, ReactNode]>; className?: string }) {
  return (
    <dl className={cn('divide-y divide-border border-y border-border text-sm', className)}>
      {items.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-4 py-2.5">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="text-right font-semibold tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
