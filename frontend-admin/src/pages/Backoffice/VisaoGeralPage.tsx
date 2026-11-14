import { Link } from 'react-router'
import { KpiCard, KpiCardSkeleton } from '@/components/backoffice/KpiCard'
import { MonthlyChart } from '@/components/backoffice/MonthlyChart'
import { PageTitle } from '@/components/backoffice/PageTitle'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useOverview } from '@/hooks/useBackoffice'
import { usePageTitle } from '@/hooks/usePageTitle'
import { brl, num, pct, rating } from '@/lib/format'
import { adminProductHref } from '@/app/links'
import { categoryLabel } from '@/lib/product'
import type { Kpis } from '@/types/product'

function kpiItems(k: Kpis): Array<{ label: string; value: string; hint?: string }> {
  return [
    { label: 'Receita', value: brl(k.revenue) },
    { label: 'Pedidos', value: num(k.orders) },
    { label: 'Unidades vendidas', value: num(k.units) },
    { label: 'Ticket médio', value: brl(k.avg_ticket, { cents: true }) },
    { label: 'Nota média', value: rating(k.avg_rating), hint: 'de 5' },
    { label: 'Entregas com atraso', value: pct(k.late_pct) },
    { label: 'Produtos', value: num(k.products) },
    { label: 'Vendedores', value: num(k.sellers) },
    { label: 'Categorias', value: num(k.categories) },
  ]
}

export default function VisaoGeralPage() {
  usePageTitle('Visão geral')
  const query = useOverview()
  const data = query.data

  return (
    <div className="space-y-8 p-4 md:p-8">
      <PageTitle title="Visão geral" description="Indicadores consolidados do período coberto pelo dataset." />

      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => query.refetch()} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:gap-4 lg:grid-cols-3">
            {data
              ? kpiItems(data.kpis).map((k) => <KpiCard key={k.label} {...k} />)
              : Array.from({ length: 9 }, (_, i) => <KpiCardSkeleton key={i} />)}
          </div>

          <section className="border border-border p-4 md:p-6">
            <h2 className="eyebrow mb-5 text-muted-foreground">Receita e unidades por mês</h2>
            {data ? <MonthlyChart data={data.monthly} /> : <Skeleton className="h-[300px] w-full" />}
          </section>

          <div className="grid gap-8 xl:grid-cols-2">
            <section>
              <div className="mb-3 flex items-end justify-between">
                <h2 className="eyebrow text-muted-foreground">Top categorias por receita</h2>
                <Link to="/categorias" className="text-xs font-bold uppercase tracking-wider hover:underline">
                  Ver todas
                </Link>
              </div>
              <div className="border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">#</TableHead>
                      <TableHead>Categoria</TableHead>
                      <TableHead className="text-right">Receita</TableHead>
                      <TableHead className="text-right">Nota</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data
                      ? data.top_categories.map((c) => (
                          <TableRow key={c.category}>
                            <TableCell className="tabular-nums text-muted-foreground">{c.rank}</TableCell>
                            <TableCell className="font-semibold">{categoryLabel(c.category)}</TableCell>
                            <TableCell className="text-right tabular-nums">{brl(c.revenue)}</TableCell>
                            <TableCell className="text-right tabular-nums">{rating(c.avg_rating)}</TableCell>
                          </TableRow>
                        ))
                      : Array.from({ length: 5 }, (_, i) => (
                          <TableRow key={i}>
                            <TableCell colSpan={4}>
                              <Skeleton className="h-5 w-full" />
                            </TableCell>
                          </TableRow>
                        ))}
                  </TableBody>
                </Table>
              </div>
            </section>

            <section>
              <div className="mb-3 flex items-end justify-between">
                <h2 className="eyebrow text-muted-foreground">Top produtos por receita</h2>
                <Link to="/produtos?sort=revenue" className="text-xs font-bold uppercase tracking-wider hover:underline">
                  Ver todos
                </Link>
              </div>
              <div className="border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">#</TableHead>
                      <TableHead>Produto</TableHead>
                      <TableHead className="text-right">Receita</TableHead>
                      <TableHead className="text-right">Unid.</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data
                      ? data.top_products.map((p) => (
                          <TableRow key={p.product_id}>
                            <TableCell className="tabular-nums text-muted-foreground">{p.rank}</TableCell>
                            <TableCell className="max-w-[14rem]">
                              <Link
                                to={adminProductHref(p.product_id)}
                                className="block truncate font-semibold underline-offset-4 hover:underline"
                                title={p.label}
                              >
                                {p.label}
                              </Link>
                              <span className="block truncate text-xs text-muted-foreground">{categoryLabel(p.category)}</span>
                            </TableCell>
                            <TableCell className="text-right tabular-nums">{brl(p.revenue)}</TableCell>
                            <TableCell className="text-right tabular-nums">{num(p.units_sold)}</TableCell>
                          </TableRow>
                        ))
                      : Array.from({ length: 5 }, (_, i) => (
                          <TableRow key={i}>
                            <TableCell colSpan={4}>
                              <Skeleton className="h-5 w-full" />
                            </TableCell>
                          </TableRow>
                        ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
