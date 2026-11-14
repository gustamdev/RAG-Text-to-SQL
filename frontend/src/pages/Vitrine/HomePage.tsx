import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router'
import { ErrorState } from '@/components/StateViews'
import { ProductCard, ProductCardSkeleton } from '@/components/product/ProductCard'
import { Skeleton } from '@/components/ui/skeleton'
import { buttonVariants } from '@/components/ui/button'
import { useCategories, useProducts } from '@/hooks/useProducts'
import { usePageTitle } from '@/hooks/usePageTitle'
import { categoryIcon } from '@/lib/categoryIcons'
import { num } from '@/lib/format'
import { categoryHref, categoryLabel } from '@/lib/product'
import { cn } from '@/lib/utils'

const FEATURED_SIZE = 12
const TOP_CATEGORIES = 12

export default function HomePage() {
  usePageTitle('')
  const featured = useProducts({ sort: 'units', page: 1, page_size: FEATURED_SIZE })
  const categories = useCategories()

  const topCategories = [...(categories.data ?? [])]
    .filter((c) => c.category !== 'sem_categoria')
    .sort((a, b) => b.units_sold - a.units_sold)
    .slice(0, TOP_CATEGORIES)

  return (
    <>
      <section className="border-b border-border">
        <div className="mx-auto grid max-w-[1600px] gap-10 px-4 py-14 md:px-8 md:py-24 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <div>
            <p className="eyebrow text-muted-foreground">Dataset Olist · e-commerce brasileiro</p>
            <h1 className="display mt-4 text-5xl md:text-7xl xl:text-8xl">
              Produtos,
              <br />
              preços e notas.
            </h1>
            <p className="mt-6 max-w-xl text-sm text-muted-foreground md:text-base">
              Navegue pelo catálogo de produtos vendidos na Olist e veja preço médio, avaliações e volume
              de vendas de cada item.
            </p>
            <div className="mt-8 flex flex-wrap gap-2">
              <Link to="/produtos" className={cn(buttonVariants({ size: 'lg' }), 'h-12 text-xs font-bold uppercase tracking-wider')}>
                Ver catálogo
                <ArrowRight aria-hidden="true" />
              </Link>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-px border border-border bg-border text-sm">
            <div className="bg-background p-5">
              <dt className="eyebrow text-muted-foreground">Produtos</dt>
              <dd className="mt-2 text-3xl font-extrabold tabular-nums">
                {featured.data ? num(featured.data.total) : <Skeleton className="h-9 w-24" />}
              </dd>
            </div>
            <div className="bg-background p-5">
              <dt className="eyebrow text-muted-foreground">Categorias</dt>
              <dd className="mt-2 text-3xl font-extrabold tabular-nums">
                {categories.data ? num(categories.data.length) : <Skeleton className="h-9 w-16" />}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="mx-auto max-w-[1600px] px-4 py-12 md:px-8 md:py-16">
        <div className="flex items-end justify-between gap-4">
          <h2 className="display text-3xl md:text-4xl">Categorias</h2>
          <Link to="/produtos" className="text-xs font-bold uppercase tracking-wider underline-offset-4 hover:underline">
            Todas
          </Link>
        </div>
        {categories.isError ? (
          <div className="mt-6">
            <ErrorState message={categories.error.message} onRetry={() => categories.refetch()} />
          </div>
        ) : (
          <ul className="mt-6 grid grid-cols-2 gap-px border border-border bg-border sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {categories.isPending
              ? Array.from({ length: TOP_CATEGORIES }, (_, i) => (
                  <li key={i} className="bg-background p-5">
                    <Skeleton className="size-6" />
                    <Skeleton className="mt-6 h-4 w-3/4" />
                    <Skeleton className="mt-2 h-3 w-1/2" />
                  </li>
                ))
              : topCategories.map((c) => {
                  const Icon = categoryIcon(c.category_en || c.category)
                  return (
                    <li key={c.category} className="bg-background">
                      <Link
                        to={categoryHref(c.category)}
                        className="flex h-full flex-col p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      >
                        <Icon className="size-6" strokeWidth={1.5} aria-hidden="true" />
                        <span className="mt-6 text-sm font-semibold leading-snug">{categoryLabel(c.category)}</span>
                        <span className="mt-1 text-xs text-muted-foreground tabular-nums">
                          {num(c.products)} produtos
                        </span>
                      </Link>
                    </li>
                  )
                })}
          </ul>
        )}
      </section>

      <section className="mx-auto max-w-[1600px] px-4 pb-16 md:px-8 md:pb-24">
        <div className="flex items-end justify-between gap-4">
          <h2 className="display text-3xl md:text-4xl">Mais vendidos</h2>
          <Link
            to="/produtos?sort=units"
            className="text-xs font-bold uppercase tracking-wider underline-offset-4 hover:underline"
          >
            Ver mais
          </Link>
        </div>
        {featured.isError ? (
          <div className="mt-6">
            <ErrorState message={featured.error.message} onRetry={() => featured.refetch()} />
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4 xl:grid-cols-6">
            {featured.isPending
              ? Array.from({ length: FEATURED_SIZE }, (_, i) => <ProductCardSkeleton key={i} />)
              : featured.data.items.map((p) => <ProductCard key={p.product_id} product={p} />)}
          </div>
        )}
      </section>
    </>
  )
}
