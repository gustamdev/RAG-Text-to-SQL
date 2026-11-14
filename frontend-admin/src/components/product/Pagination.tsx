import { ChevronLeft, ChevronRight } from 'lucide-react'
import { pageWindow, totalPages } from '@/lib/pagination'
import { cn } from '@/lib/utils'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  className?: string
}

const cell =
  'inline-flex h-9 min-w-9 items-center justify-center border border-input px-2 text-xs font-bold tabular-nums transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40'

/** Paginação server-side: o pai guarda `page` (na URL) e busca só a página pedida. */
export function Pagination({ page, pageSize, total, onPageChange, className }: PaginationProps) {
  const pages = totalPages(total, pageSize)
  if (pages <= 1) return null
  const items = pageWindow(page, pages)

  return (
    <nav aria-label="Paginação" className={cn('flex flex-wrap items-center justify-center gap-1', className)}>
      <button type="button" className={cell} disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        <ChevronLeft className="size-4" aria-hidden="true" />
        <span className="sr-only">Página anterior</span>
      </button>
      {items.map((item, index) =>
        item === 'gap' ? (
          <span key={`gap-${index}`} aria-hidden="true" className="px-1 text-muted-foreground">
            …
          </span>
        ) : (
          <button
            key={item}
            type="button"
            aria-current={item === page ? 'page' : undefined}
            aria-label={`Página ${item}`}
            className={cn(cell, item === page && 'border-foreground bg-foreground text-background hover:bg-foreground')}
            onClick={() => onPageChange(item)}
          >
            {item}
          </button>
        ),
      )}
      <button type="button" className={cell} disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
        <ChevronRight className="size-4" aria-hidden="true" />
        <span className="sr-only">Próxima página</span>
      </button>
    </nav>
  )
}
