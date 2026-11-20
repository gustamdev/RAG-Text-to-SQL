import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useRef } from 'react'
import { Link } from 'react-router'
import { ErrorState } from '@/components/StateViews'
import type { ProductCard as Card } from '@/types/shop'
import { ProductCard, ProductCardSkeleton } from './ProductCard'

/** Faixa horizontal com scroll-snap nativo e setas; sem auto-play. */
export function ProductShelf({
  title,
  href,
  products,
  loading,
  error,
  onRetry,
}: {
  title: string
  href?: string
  products: Card[] | undefined
  loading: boolean
  error: boolean
  onRetry: () => void
}) {
  const ref = useRef<HTMLUListElement>(null)
  const scroll = (dir: 1 | -1) =>
    ref.current?.scrollBy({
      left: dir * ref.current.clientWidth * 0.8,
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    })
  const arrow =
    'hidden size-9 items-center justify-center border border-input hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring md:inline-flex'

  return (
    <section aria-label={title} className="py-8 md:py-10">
      <div className="mb-4 flex items-end justify-between gap-4">
        <h2 className="text-xl font-extrabold tracking-tight md:text-2xl">{title}</h2>
        <div className="flex items-center gap-2">
          {href && (
            <Link to={href} className="text-sm font-semibold underline underline-offset-4">
              Ver todos
            </Link>
          )}
          <button type="button" className={arrow} onClick={() => scroll(-1)}>
            <ChevronLeft className="size-4" aria-hidden="true" />
            <span className="sr-only">Anterior</span>
          </button>
          <button type="button" className={arrow} onClick={() => scroll(1)}>
            <ChevronRight className="size-4" aria-hidden="true" />
            <span className="sr-only">Próximos</span>
          </button>
        </div>
      </div>
      {error ? (
        <ErrorState onRetry={onRetry} />
      ) : (
        <ul ref={ref} className="no-scrollbar -mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 md:mx-0 md:gap-4 md:px-0">
          {loading || !products
            ? Array.from({ length: 6 }, (_, i) => (
                <li key={i} className="w-[44%] shrink-0 snap-start md:w-[calc((100%-5*1rem)/6)]">
                  <ProductCardSkeleton />
                </li>
              ))
            : products.map((p) => (
                <li key={p.product_id} className="w-[44%] shrink-0 snap-start md:w-[calc((100%-5*1rem)/6)]">
                  <ProductCard product={p} className="h-full" />
                </li>
              ))}
        </ul>
      )}
    </section>
  )
}
