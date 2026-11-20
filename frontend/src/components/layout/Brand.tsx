import { Link } from 'react-router'
import { cn } from '@/lib/utils'

/** Monograma: três barras de gráfico num quadrado preto. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('size-7 shrink-0', className)}>
      <rect width="32" height="32" fill="currentColor" />
      <rect x="7" y="17" width="4.5" height="8" fill="var(--background)" />
      <rect x="13.75" y="11" width="4.5" height="14" fill="var(--background)" />
      <rect x="20.5" y="6" width="4.5" height="19" fill="var(--background)" />
    </svg>
  )
}

export function Brand({
  to = '/',
  suffix,
  className,
  onClick,
}: {
  to?: string
  suffix?: string
  className?: string
  onClick?: () => void
}) {
  return (
    <Link to={to} onClick={onClick} className={cn('inline-flex items-center gap-2.5', className)}>
      <BrandMark />
      <span className="text-sm font-extrabold uppercase tracking-tight">Loja Olist</span>
      {suffix && <span className="eyebrow border-l border-border pl-2.5 text-muted-foreground">{suffix}</span>}
    </Link>
  )
}
