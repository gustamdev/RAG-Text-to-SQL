import { PageTitle } from '@/components/backoffice/PageTitle'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Link } from 'react-router'
import { useAdminCategories } from '@/hooks/useBackoffice'
import { usePageTitle } from '@/hooks/usePageTitle'
import { categoryIcon } from '@/lib/categoryIcons'
import { brl, num, pct, rating } from '@/lib/format'
import { categoryLabel } from '@/lib/product'

export default function CategoriasPage() {
  usePageTitle('Categorias')
  const query = useAdminCategories()
  const rows = query.data

  return (
    <div className="space-y-6 p-4 md:p-8">
      <PageTitle title="Categorias" description="Ranking por receita. Clique numa categoria para ver os produtos dela." />

      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => query.refetch()} />
      ) : (
        <div className="border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">#</TableHead>
                <TableHead>Categoria</TableHead>
                <TableHead className="text-right">Produtos</TableHead>
                <TableHead className="text-right">Unid.</TableHead>
                <TableHead className="text-right">Receita</TableHead>
                <TableHead className="text-right">Preço médio</TableHead>
                <TableHead className="text-right">Nota</TableHead>
                <TableHead className="text-right">% ruins</TableHead>
                <TableHead className="text-right">% atraso</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows
                ? rows.map((c) => {
                    const Icon = categoryIcon(c.category_en || c.category)
                    return (
                      <TableRow key={c.category}>
                        <TableCell className="tabular-nums text-muted-foreground">{c.rank}</TableCell>
                        <TableCell>
                          <Link
                            to={`/produtos?category=${encodeURIComponent(c.category)}`}
                            className="inline-flex items-center gap-2.5 font-semibold underline-offset-4 hover:underline"
                          >
                            <Icon className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden="true" />
                            {categoryLabel(c.category)}
                          </Link>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{num(c.products)}</TableCell>
                        <TableCell className="text-right tabular-nums">{num(c.units_sold)}</TableCell>
                        <TableCell className="text-right tabular-nums">{brl(c.revenue)}</TableCell>
                        <TableCell className="text-right tabular-nums">{brl(c.avg_price, { cents: true })}</TableCell>
                        <TableCell className="text-right tabular-nums">{rating(c.avg_rating)}</TableCell>
                        <TableCell className="text-right tabular-nums">{pct(c.bad_review_pct)}</TableCell>
                        <TableCell className="text-right tabular-nums">{pct(c.late_pct)}</TableCell>
                      </TableRow>
                    )
                  })
                : Array.from({ length: 12 }, (_, i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={9}>
                        <Skeleton className="h-6 w-full" />
                      </TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
