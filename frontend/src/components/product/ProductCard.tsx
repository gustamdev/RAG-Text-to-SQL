import { Link } from 'react-router'
import { num } from '@/lib/format'
import { productHref } from '@/lib/product'
import { cn } from '@/lib/utils'
import type { ProductCard as Card } from '@/types/shop'
import { PriceBlock } from './ProductBits'
import { ProductThumb } from './ProductThumb'
import { RatingStars } from './RatingStars'

export function ProductCard({ product, className }: { product: Card; className?: string }) {
  const out = product.stock < 1
  return (
    <Link
      to={productHref(product.product_id)}
      className={cn(
        'group relative flex flex-col border border-border bg-card transition-colors hover:border-foreground focus-visible:outline-2 focus-visible:outline-ring',
        className,
      )}
    >
      <ProductThumb
        imageUrl={product.image_url}
        alt={product.title}
        className={cn('aspect-square', out && 'opacity-60')}
      />
      {out && <span className="absolute left-0 top-0 bg-foreground px-2 py-1 text-[11px] font-bold uppercase text-background">Esgotado</span>}
      {!out && product.stock <= 5 && (
        <span className="absolute left-0 top-0 bg-brand px-2 py-1 text-[11px] font-bold uppercase text-brand-foreground">
          Restam {product.stock}
        </span>
      )}
      <div className="flex flex-1 flex-col gap-2 p-3 md:p-4">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug break-words">{product.title}</h3>
        <RatingStars value={product.avg_rating} count={product.review_count} />
        <div className="mt-auto pt-1">
          <PriceBlock cents={product.price_cents} />
          <p className="mt-1 text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">Entrega por CEP</span> · {num(product.units_sold)} vendidos
          </p>
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
        <div className="h-4 w-4/5 animate-pulse bg-muted motion-reduce:animate-none" />
        <div className="h-3 w-2/3 animate-pulse bg-muted motion-reduce:animate-none" />
        <div className="h-5 w-1/3 animate-pulse bg-muted motion-reduce:animate-none" />
      </div>
    </div>
  )
}
