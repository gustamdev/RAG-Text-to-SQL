import { createElement } from 'react'
import { categoryIcon } from '@/lib/categoryIcons'
import { cn } from '@/lib/utils'

/**
 * Placeholder do produto: a Olist não tem foto, então a "imagem" é o ícone da categoria
 * sobre um fundo neutro. Decorativo (o rótulo do produto já está no texto ao lado).
 */
export function ProductThumb({
  category,
  className,
  iconClassName,
}: {
  category: string
  className?: string
  iconClassName?: string
}) {
  return (
    <div aria-hidden="true" className={cn('flex items-center justify-center bg-surface text-foreground/70', className)}>
      {createElement(categoryIcon(category), { strokeWidth: 1.25, className: cn('size-1/3', iconClassName) })}
    </div>
  )
}
