import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { ProductCard } from '@/components/product/ProductCard'
import { ProductThumb } from '@/components/product/ProductThumb'
import { RatingStars } from '@/components/product/RatingStars'
import { Specs } from '@/components/product/Specs'
import { Skeleton } from '@/components/ui/skeleton'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useProduct } from '@/hooks/useProducts'
import { brl, measure, num, weight } from '@/lib/format'
import { categoryHref, categoryLabel } from '@/lib/product'
import { ApiError } from '@/services/http'

function DetailSkeleton() {
  return (
    <div className="grid gap-10 lg:grid-cols-2" aria-hidden="true">
      <Skeleton className="aspect-square w-full" />
      <div className="space-y-4">
        <Skeleton className="h-3 w-1/4" />
        <Skeleton className="h-9 w-3/4" />
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  )
}

export default function ProdutoPage() {
  const { id } = useParams()
  const query = useProduct(id)
  const product = query.data
  usePageTitle(product ? product.label : 'Produto')

  const notFound = query.error instanceof ApiError && query.error.status === 404

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-8 md:px-8 md:py-12">
      <Link
        to="/produtos"
        className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Catálogo
      </Link>

      <div className="mt-8">
        {query.isPending ? (
          <DetailSkeleton />
        ) : notFound ? (
          <EmptyState
            title="Produto não encontrado"
            text="O código não existe no catálogo ou foi digitado errado."
            actionTo="/produtos"
            actionLabel="Ver catálogo"
          />
        ) : query.isError ? (
          <ErrorState message={query.error.message} onRetry={() => query.refetch()} />
        ) : (
          product && (
            <>
              <div className="grid gap-8 lg:grid-cols-2 lg:gap-14">
                <div>
                  <ProductThumb category={product.category_en || product.category} className="aspect-square w-full border border-border" />
                  <p className="mt-2 text-xs text-muted-foreground">
                    O dataset Olist não tem foto de produto
                    {product.photos_qty !== null ? ` (o anúncio original tinha ${product.photos_qty} ${product.photos_qty === 1 ? 'foto' : 'fotos'})` : ''}.
                  </p>
                </div>

                <div>
                  <Link
                    to={categoryHref(product.category)}
                    className="eyebrow text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  >
                    {categoryLabel(product.category)}
                  </Link>
                  <h1 className="mt-3 text-3xl font-extrabold leading-tight tracking-tight break-words md:text-4xl">
                    {product.label}
                  </h1>
                  <p className="mt-6 text-4xl font-extrabold tabular-nums">{brl(product.avg_price, { cents: true })}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Preço médio praticado</p>
                  <RatingStars className="mt-5 text-sm" value={product.avg_rating} count={product.review_count} />

                  <dl className="mt-8 grid grid-cols-3 gap-px border border-border bg-border">
                    {(
                      [
                        ['Unidades vendidas', num(product.units_sold)],
                        ['Avaliações', num(product.review_count)],
                        ['Fotos no anúncio', product.photos_qty === null ? '—' : num(product.photos_qty)],
                      ] as const
                    ).map(([label, value]) => (
                      <div key={label} className="bg-background p-4">
                        <dt className="eyebrow text-muted-foreground">{label}</dt>
                        <dd className="mt-2 text-xl font-extrabold tabular-nums">{value}</dd>
                      </div>
                    ))}
                  </dl>

                  <h2 className="eyebrow mt-10 text-muted-foreground">Atributos físicos</h2>
                  <Specs
                    className="mt-3"
                    items={[
                      ['Peso', weight(product.weight_g)],
                      ['Comprimento', measure(product.length_cm, 'cm')],
                      ['Altura', measure(product.height_cm, 'cm')],
                      ['Largura', measure(product.width_cm, 'cm')],
                      ['Caracteres no título', product.name_length === null ? '—' : num(product.name_length)],
                      ['Caracteres na descrição', product.description_length === null ? '—' : num(product.description_length)],
                    ]}
                  />
                </div>
              </div>

              {product.related.length > 0 && (
                <section className="mt-16 border-t border-border pt-10">
                  <h2 className="display text-2xl md:text-3xl">Relacionados</h2>
                  <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4 xl:grid-cols-6">
                    {product.related.map((p) => (
                      <ProductCard key={p.product_id} product={p} />
                    ))}
                  </div>
                </section>
              )}
            </>
          )
        )}
      </div>
    </div>
  )
}
