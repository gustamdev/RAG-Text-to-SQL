import { Link } from 'react-router'
import { Button } from '@/components/ui/button'

export function EmptyState({
  title,
  text,
  actionTo,
  actionLabel,
}: {
  title: string
  text?: string
  actionTo?: string
  actionLabel?: string
}) {
  return (
    <div className="border border-dashed border-border py-20 text-center">
      <p className="display text-2xl">{title}</p>
      {text && <p className="mt-2 text-sm text-muted-foreground">{text}</p>}
      {actionTo && actionLabel && (
        <Link
          to={actionTo}
          className="mt-6 inline-block bg-primary px-6 py-3 text-xs font-bold uppercase tracking-wider text-primary-foreground"
        >
          {actionLabel}
        </Link>
      )}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="border border-dashed border-destructive/50 py-16 text-center">
      <p className="display text-2xl">Não foi possível carregar</p>
      <p className="mt-2 text-sm text-muted-foreground">{message ?? 'Tente novamente em instantes.'}</p>
      {onRetry && (
        <Button className="mt-6" variant="outline" onClick={onRetry}>
          Tentar de novo
        </Button>
      )}
    </div>
  )
}

export function LoadingBlock({ label = 'Carregando…' }: { label?: string }) {
  return (
    <div role="status" className="animate-pulse py-16 text-center text-sm text-muted-foreground">
      {label}
    </div>
  )
}

export function InlineError({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <p id={id} role="alert" className="mt-1 text-sm font-medium text-destructive">
      {children}
    </p>
  )
}
