import { ArrowDown, ArrowUp, ArrowUpDown, Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { PageTitle } from '@/components/backoffice/PageTitle'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Pagination } from '@/components/product/Pagination'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAdminProducts } from '@/hooks/useBackoffice'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useCategories } from '@/hooks/useProducts'
import { brl, num, pct, rating } from '@/lib/format'
import { backofficeProductHref, categoryLabel } from '@/lib/product'
import { enumParam, floatParam, intParam, withParams } from '@/lib/searchParams'
import { cn } from '@/lib/utils'
import type { AdminProductSort, SortOrder } from '@/types/product'

const PAGE_SIZE = 25
const SORTS: readonly AdminProductSort[] = ['units', 'revenue', 'rating', 'price', 'bad_review_pct', 'late_pct']
const ORDERS: readonly SortOrder[] = ['asc', 'desc']
const MIN_RATINGS = [3, 3.5, 4, 4.5]

function SortHead({
  label,
  column,
  sort,
  order,
  onSort,
  className,
}: {
  label: string
  column: AdminProductSort
  sort: AdminProductSort
  order: SortOrder
  onSort: (column: AdminProductSort) => void
  className?: string
}) {
  const active = sort === column
  const Icon = !active ? ArrowUpDown : order === 'asc' ? ArrowUp : ArrowDown
  return (
    <TableHead
      aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={cn('whitespace-nowrap px-0', className)}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={cn(
          'inline-flex h-10 items-center gap-1.5 px-2 text-xs font-bold uppercase tracking-wider hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          active && 'text-foreground',
        )}
      >
        {label}
        <Icon className={cn('size-3.5', !active && 'opacity-40')} aria-hidden="true" />
      </button>
    </TableHead>
  )
}

export default function ProdutosAdminPage() {
  usePageTitle('Produtos')
  const [params, setParams] = useSearchParams()

  const q = params.get('q') ?? ''
  const category = params.get('category') ?? ''
  const minRating = floatParam(params, 'min_rating')
  const sort = enumParam(params, 'sort', SORTS, 'units')
  const order = enumParam(params, 'order', ORDERS, 'desc')
  const page = intParam(params, 'page', 1)

  const [search, setSearch] = useState(q)
  const debouncedSearch = useDebouncedValue(search.trim())
  const pushedQ = useRef(q)
  useEffect(() => {
    if (debouncedSearch === pushedQ.current) return
    pushedQ.current = debouncedSearch
    setParams((current) => withParams(current, { q: debouncedSearch, page: undefined }), { replace: true })
  }, [debouncedSearch, setParams])
  useEffect(() => {
    if (q === pushedQ.current) return
    pushedQ.current = q
    setSearch(q)
  }, [q])

  const categories = useCategories()
  const query = useAdminProducts({
    ...(q ? { q } : {}),
    ...(category ? { category } : {}),
    ...(minRating !== undefined ? { min_rating: minRating } : {}),
    sort,
    order,
    page,
    page_size: PAGE_SIZE,
  })
  const data = query.data
  const hasFilters = q !== '' || category !== '' || minRating !== undefined

  function update(changes: Record<string, string | number | undefined>) {
    setParams((current) => withParams(current, { page: undefined, ...changes }))
  }

  function onSort(column: AdminProductSort) {
    if (column === sort) update({ order: order === 'desc' ? 'asc' : 'desc' })
    else update({ sort: column, order: 'desc' })
  }

  function clearFilters() {
    setSearch('')
    setParams((current) => withParams(current, { q: undefined, category: undefined, min_rating: undefined, page: undefined }))
  }

  const head = { sort, order, onSort }

  return (
    <div className="space-y-6 p-4 md:p-8">
      <PageTitle title="Produtos" description="Métricas por produto. Clique nos títulos das colunas para ordenar." />

      <form
        role="search"
        onSubmit={(e) => e.preventDefault()}
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[2fr_1.4fr_1fr_auto] lg:items-end"
      >
        <div className="sm:col-span-2 lg:col-span-1">
          <Label htmlFor="q" className="eyebrow">
            Buscar
          </Label>
          <div className="relative mt-2">
            <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="q"
              type="search"
              className="h-11 pl-9"
              placeholder="Produto ou categoria"
              maxLength={100}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        <div>
          <Label htmlFor="category" className="eyebrow">
            Categoria
          </Label>
          <Select id="category" className="mt-2 h-11" value={category} onChange={(e) => update({ category: e.target.value })}>
            <option value="">Todas as categorias</option>
            {category && !categories.data?.some((c) => c.category === category) && (
              <option value={category}>{categoryLabel(category)}</option>
            )}
            {categories.data?.map((c) => (
              <option key={c.category} value={c.category}>
                {categoryLabel(c.category)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="min_rating" className="eyebrow">
            Nota mínima
          </Label>
          <Select
            id="min_rating"
            className="mt-2 h-11"
            value={minRating === undefined ? '' : String(minRating)}
            onChange={(e) => update({ min_rating: e.target.value })}
          >
            <option value="">Qualquer nota</option>
            {MIN_RATINGS.map((r) => (
              <option key={r} value={r}>
                {rating(r)} ou mais
              </option>
            ))}
          </Select>
        </div>
        {hasFilters && (
          <Button type="button" variant="ghost" className="h-11 text-xs font-bold uppercase tracking-wider" onClick={clearFilters}>
            <X aria-hidden="true" />
            Limpar
          </Button>
        )}
      </form>

      <p className="text-sm text-muted-foreground" aria-live="polite">
        {data ? `${num(data.total)} ${data.total === 1 ? 'produto' : 'produtos'}` : ' '}
      </p>

      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => query.refetch()} />
      ) : data && data.total === 0 ? (
        <EmptyState title="Nenhum produto encontrado" text="Ajuste a busca ou os filtros." />
      ) : (
        <div className={cn('border border-border transition-opacity', query.isPlaceholderData && 'opacity-50')}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">#</TableHead>
                <TableHead>Produto</TableHead>
                <SortHead label="Preço" column="price" {...head} className="text-right [&>button]:flex-row-reverse" />
                <SortHead label="Unid." column="units" {...head} className="text-right [&>button]:flex-row-reverse" />
                <SortHead label="Receita" column="revenue" {...head} className="text-right [&>button]:flex-row-reverse" />
                <SortHead label="Nota" column="rating" {...head} className="text-right [&>button]:flex-row-reverse" />
                <SortHead label="% ruins" column="bad_review_pct" {...head} className="text-right [&>button]:flex-row-reverse" />
                <SortHead label="% atraso" column="late_pct" {...head} className="text-right [&>button]:flex-row-reverse" />
                <TableHead className="text-right">Vend.</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data
                ? data.items.map((p) => (
                    <TableRow key={p.product_id}>
                      <TableCell className="tabular-nums text-muted-foreground">{p.rank}</TableCell>
                      <TableCell className="max-w-[18rem]">
                        <Link
                          to={backofficeProductHref(p.product_id)}
                          className="block truncate font-semibold underline-offset-4 hover:underline"
                          title={p.label}
                        >
                          {p.label}
                        </Link>
                        <span className="block truncate text-xs text-muted-foreground">{categoryLabel(p.category)}</span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{brl(p.avg_price, { cents: true })}</TableCell>
                      <TableCell className="text-right tabular-nums">{num(p.units_sold)}</TableCell>
                      <TableCell className="text-right tabular-nums">{brl(p.revenue)}</TableCell>
                      <TableCell className="text-right tabular-nums">{rating(p.avg_rating)}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(p.bad_review_pct)}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(p.late_pct)}</TableCell>
                      <TableCell className="text-right tabular-nums">{num(p.sellers)}</TableCell>
                    </TableRow>
                  ))
                : Array.from({ length: 10 }, (_, i) => (
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

      {data && data.total > 0 && (
        <Pagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          onPageChange={(next) => update({ page: next > 1 ? next : undefined })}
        />
      )}
    </div>
  )
}
