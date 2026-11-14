import type { ReactNode } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function KpiCard({
  label,
  value,
  hint,
  className,
}: {
  label: string
  value: ReactNode
  hint?: string
  className?: string
}) {
  return (
    <div className={cn('border border-border bg-card p-4 md:p-5', className)}>
      <p className="eyebrow text-muted-foreground">{label}</p>
      <p className="mt-3 text-2xl font-extrabold tracking-tight tabular-nums md:text-3xl">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function KpiCardSkeleton() {
  return (
    <div className="border border-border p-4 md:p-5" aria-hidden="true">
      <Skeleton className="h-3 w-1/2" />
      <Skeleton className="mt-4 h-8 w-3/4" />
    </div>
  )
}
