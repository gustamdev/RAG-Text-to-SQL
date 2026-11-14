import type { ReactNode } from 'react'

/** Cabeçalho de tela do backoffice (menor que o PageHeader da vitrine). */
export function PageTitle({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="display text-3xl md:text-4xl">{title}</h1>
        {description && <p className="mt-3 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  )
}
