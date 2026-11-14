import { ArrowLeft, ExternalLink } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { KpiCard, KpiCardSkeleton } from '@/components/backoffice/KpiCard'
import { MonthlyChart } from '@/components/backoffice/MonthlyChart'
import { RatingBars } from '@/components/backoffice/RatingBars'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Specs } from '@/components/product/Specs'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAdminProduct } from '@/hooks/useBackoffice'
import { usePageTitle } from '@/hooks/usePageTitle'
import { brl, measure, num, pct, rating, weight } from '@/lib/format'
import { adminProductHref } from '@/app/links'
import { categoryLabel } from '@/lib/product'
import { ApiError } from '@/services/http'
import type { AdminProductDetail } from '@/types/product'

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border border-border p-4 md:p-6">
      <h2 className="eyebrow mb-5 text-muted-foreground">{title}</h2>
      {children}
    </section>
  )
}

function Metrics({ p }: { p: AdminProductDetail }) {
  const items: Array<[string, string, string?]> = [
    ['Receita', brl(p.revenue)],
    ['Unidades vendidas', num(p.units_sold)],
    ['Preço médio', brl(p.avg_price, { cents: true })],
    ['Frete médio', brl(p.freight_avg, { cents: true })],
    ['Nota média', rating(p.avg_rating), `${num(p.review_count)} avaliações`],
    ['Avaliações ruins', pct(p.bad_review_pct), 'notas 1 e 2'],
    ['Entregas com atraso', pct(p.late_pct)],
    ['Vendedores', num(p.sellers)],
  ]
  return (
    <div className="grid grid-cols-2 gap-3 md:gap-4 lg:grid-cols-4">
      {items.map(([label, value, hint]) => (
        <KpiCard key={label} label={label} value={value} {...(hint ? { hint } : {})} />
      ))}
    </div>
  )
}

export default function ProdutoAdminPage() {
  const { id } = useParams()
  const query = useAdminProduct(id)
  const p = query.data
  usePageTitle(p ? p.label : 'Produto')
  const notFound = query.error instanceof ApiError && query.error.status === 404

  return (
    <div className="space-y-8 p-4 md:p-8">
      <Link
        to="/produtos"
        className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Produtos
      </Link>

      {query.isPending ? (
        <div className="space-y-8" aria-hidden="true">
          <div className="space-y-3">
            <Skeleton className="h-3 w-40" />
            <Skeleton className="h-9 w-2/3" />
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 8 }, (_, i) => (
              <KpiCardSkeleton key={i} />
            ))}
          </div>
        </div>
      ) : notFound ? (
        <EmptyState
          title="Produto não encontrado"
          text="O código não existe no dataset."
          actionTo="/produtos"
          actionLabel="Voltar à lista"
        />
      ) : query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => query.refetch()} />
      ) : (
        p && (
          <>
            <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0">
                <p className="eyebrow text-muted-foreground">
                  <Link to={`/produtos?category=${encodeURIComponent(p.category)}`} className="hover:text-foreground hover:underline">
                    {categoryLabel(p.category)}
                  </Link>
                  <span aria-hidden="true"> · </span>#{p.rank} no ranking
                </p>
                <h1 className="mt-3 text-3xl font-extrabold leading-tight tracking-tight break-words md:text-4xl">{p.label}</h1>
              </div>
              <Link
                to={adminProductHref(p.product_id)}
                className="inline-flex shrink-0 items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                Ver na vitrine
                <ExternalLink className="size-4" aria-hidden="true" />
              </Link>
            </header>

            <Metrics p={p} />

            <div className="grid gap-8 xl:grid-cols-[1.6fr_1fr]">
              <Panel title="Receita e unidades por mês">
                <MonthlyChart data={p.monthly} height={260} />
              </Panel>
              <Panel title="Distribuição das notas">
                <RatingBars data={p.rating_distribution} />
              </Panel>
            </div>

            <div className="grid gap-8 xl:grid-cols-[1.6fr_1fr]">
              <section>
                <h2 className="eyebrow mb-3 text-muted-foreground">Top vendedores</h2>
                <div className="border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Vendedor</TableHead>
                        <TableHead>UF</TableHead>
                        <TableHead className="text-right">Unid.</TableHead>
                        <TableHead className="text-right">Receita</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {p.top_sellers.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                            Sem vendas registradas.
                          </TableCell>
                        </TableRow>
                      ) : (
                        p.top_sellers.map((s) => (
                          <TableRow key={s.seller_id}>
                            <TableCell className="font-mono text-xs" title={s.seller_id}>
                              {s.seller_id.slice(0, 8)}
                            </TableCell>
                            <TableCell>{s.seller_state ?? '—'}</TableCell>
                            <TableCell className="text-right tabular-nums">{num(s.units)}</TableCell>
                            <TableCell className="text-right tabular-nums">{brl(s.revenue)}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              </section>

              <section>
                <h2 className="eyebrow mb-3 text-muted-foreground">Atributos físicos</h2>
                <Specs
                  items={[
                    ['Peso', weight(p.weight_g)],
                    ['Comprimento', measure(p.length_cm, 'cm')],
                    ['Altura', measure(p.height_cm, 'cm')],
                    ['Largura', measure(p.width_cm, 'cm')],
                    ['Fotos no anúncio', p.photos_qty === null ? '—' : num(p.photos_qty)],
                    ['Caracteres no título', p.name_length === null ? '—' : num(p.name_length)],
                    ['Caracteres na descrição', p.description_length === null ? '—' : num(p.description_length)],
                  ]}
                />
              </section>
            </div>
          </>
        )
      )}
    </div>
  )
}
