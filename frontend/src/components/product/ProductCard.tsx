import { Link } from 'react-router'
import { brl, num } from '@/lib/format'
import { categoryLabel, productHref } from '@/lib/product'
import type { ProductSummary } from '@/types/product'
import { ProductThumb } from './ProductThumb'
import { RatingStars } from './RatingStars'

export function ProductCard({ product }: { product: ProductSummary }) {
  return (
    <Link
      to={productHref(product.product_id)}
      className="group flex flex-col border border-border bg-card transition-colors hover:border-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <ProductThumb category={product.category_en || product.category} className="aspect-square" />
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <p className="eyebrow truncate text-muted-foreground">{categoryLabel(product.category)}</p>
          <h3 className="mt-1.5 line-clamp-2 text-sm font-semibold leading-snug break-words">{product.label}</h3>
        </div>
        <RatingStars value={product.avg_rating} count={product.review_count} />
        <div className="mt-auto flex items-baseline justify-between gap-2 border-t border-border pt-3">
          <p className="text-base font-extrabold tabular-nums">{brl(product.avg_price, { cents: true })}</p>
          <p className="text-xs text-muted-foreground tabular-nums">{num(product.units_sold)} vendidos</p>
        </div>
      </div>
    </Link>
  )
}

export function ProductCardSkeleton() {
  return (
    <div className="border border-border" aria-hidden="true">
      <div className="aspect-square animate-pulse bg-muted motion-reduce:animate-none" />
      <div className="space-y-3 p-4">
        <div className="h-3 w-1/2 animate-pulse bg-muted motion-reduce:animate-none" />
        <div className="h-4 w-4/5 animate-pulse bg-muted motion-reduce:animate-none" />
        <div className="h-3 w-2/3 animate-pulse bg-muted motion-reduce:animate-none" />
        <div className="h-5 w-1/3 animate-pulse bg-muted motion-reduce:animate-none" />
      </div>
    </div>
  )
}
