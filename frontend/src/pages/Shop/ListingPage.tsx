import { SlidersHorizontal, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { FilterPanel } from '@/components/product/FilterPanel'
import { Pagination } from '@/components/product/Pagination'
import { ProductCard, ProductCardSkeleton } from '@/components/product/ProductCard'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useCategories, useProducts } from '@/hooks/useShop'
import { num } from '@/lib/format'
import { categoryHref } from '@/lib/product'
import { enumParam, floatParam, intParam, withParams } from '@/lib/searchParams'
import type { ProductSort } from '@/types/shop'

const SORTS: readonly ProductSort[] = ['best_selling', 'price_asc', 'price_desc', 'rating', 'newest']
const SORT_LABEL: Record<ProductSort, string> = {
  best_selling: 'Mais vendidos',
  price_asc: 'Menor preço',
  price_desc: 'Maior preço',
  rating: 'Melhor avaliados',
  newest: 'Mais recentes',
}

/** Categoria (/c/:categoria) e busca (/busca?q=): mesma listagem, estado todo na URL. */
export default function ListingPage() {
  const { categoria } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [sheet, setSheet] = useState(false)
  const cats = useCategories()

  const category = categoria ?? params.get('category') ?? ''
  const q = params.get('q') ?? ''
  const sort = enumParam(params, 'sort', SORTS, 'best_selling')
  const page = intParam(params, 'page', 1)
  const minPrice = floatParam(params, 'min_price')
  const maxPrice = floatParam(params, 'max_price')
  const minRating = floatParam(params, 'min_rating')
  const minReviews = floatParam(params, 'min_reviews')
  const inStock = params.get('in_stock') === 'true'

  const query = useProducts({
    ...(q && { q }),
    ...(category && { category }),
    ...(minPrice !== undefined && { min_price_cents: Math.round(minPrice * 100) }),
    ...(maxPrice !== undefined && { max_price_cents: Math.round(maxPrice * 100) }),
    ...(minRating !== undefined && { min_rating: minRating }),
    ...(minReviews !== undefined && { min_reviews: minReviews }),
    ...(inStock && { in_stock: true }),
    sort,
    page,
    page_size: 24,
  })

  const label = cats.data?.find((c) => c.category === category)?.label
  const title = q ? `Resultados para "${q}"` : (label ?? 'Todos os produtos')
  usePageTitle(title)

  const change = (changes: Record<string, string | undefined>) => setParams(withParams(params, { ...changes, page: undefined }))
  const onCategory = (c: string) => {
    const rest = params.toString() ? `?${params}` : ''
    if (categoria) navigate((c ? categoryHref(c) : '/busca') + rest)
    else change({ category: c || undefined })
  }

  const chips: { key: string; text: string; clear: Record<string, undefined> }[] = [
    ...(minRating !== undefined ? [{ key: 'r', text: `Nota ${minRating}+`, clear: { min_rating: undefined } }] : []),
    ...(minPrice !== undefined ? [{ key: 'a', text: `A partir de R$ ${minPrice}`, clear: { min_price: undefined } }] : []),
    ...(maxPrice !== undefined ? [{ key: 'b', text: `Até R$ ${maxPrice}`, clear: { max_price: undefined } }] : []),
    ...(inStock ? [{ key: 's', text: 'Em estoque', clear: { in_stock: undefined } }] : []),
  ]
  const panel = (
    <FilterPanel
      key={params.toString()}
      value={{ category, minPrice: minPrice?.toString() ?? '', maxPrice: maxPrice?.toString() ?? '', minRating: minRating?.toString() ?? '', inStock }}
      categories={cats.data}
      onChange={change}
      onCategory={onCategory}
    />
  )
  const total = query.data?.total ?? 0

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-6 md:px-8">
      <nav aria-label="Trilha" className="mb-2 text-xs text-muted-foreground">
        <Link to="/" className="hover:underline">Início</Link> / <span>{label ?? (q ? 'Busca' : 'Produtos')}</span>
      </nav>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-extrabold tracking-tight md:text-4xl">{title}</h1>
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground tabular-nums">
          {query.data ? `${num(total)} produtos` : ''}
        </p>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <button type="button" onClick={() => setSheet(true)} className="inline-flex h-11 items-center gap-2 border border-input px-4 text-sm font-bold md:hidden">
          <SlidersHorizontal className="size-4" aria-hidden="true" />
          Filtros{chips.length ? ` (${chips.length})` : ''}
        </button>
        <label className="ml-auto flex items-center gap-2 text-sm">
          <span className="hidden font-semibold sm:inline">Ordenar</span>
          <select value={sort} onChange={(e) => change({ sort: e.target.value })} className="h-11 border border-input bg-background px-2 text-base md:h-9 md:text-sm">
            {SORTS.map((s) => (<option key={s} value={s}>{SORT_LABEL[s]}</option>))}
          </select>
        </label>
      </div>

      {chips.length > 0 && (
        <ul className="mb-4 flex flex-wrap items-center gap-2">
          {chips.map((c) => (
            <li key={c.key}>
              <button type="button" onClick={() => change(c.clear)} className="inline-flex min-h-9 items-center gap-1.5 border border-foreground px-3 text-xs font-bold">
                {c.text}<X className="size-3.5" aria-hidden="true" /><span className="sr-only">Remover filtro</span>
              </button>
            </li>
          ))}
          <li><button type="button" onClick={() => setParams(withParams(params, { min_rating: undefined, min_price: undefined, max_price: undefined, in_stock: undefined, min_reviews: undefined, page: undefined }))} className="text-xs font-bold underline">Limpar filtros</button></li>
        </ul>
      )}

      <div className="grid gap-8 md:grid-cols-[220px_1fr]">
        <aside aria-label="Filtros" className="hidden md:block">{panel}</aside>
        <div>
          {query.isError ? (
            <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />
          ) : query.isLoading ? (
            <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 xl:grid-cols-4">
              {Array.from({ length: 8 }, (_, i) => (<li key={i}><ProductCardSkeleton /></li>))}
            </ul>
          ) : query.data && query.data.items.length === 0 ? (
            <div>
              <EmptyState title="Nenhum produto encontrado" text={q ? `Nada para "${q}". Confira a escrita ou tente uma categoria.` : 'Nenhum produto com esses filtros.'} />
              <div className="mt-4 flex flex-wrap gap-2">
                {chips.length > 0 && <button type="button" className="h-11 border border-input px-4 text-sm font-bold" onClick={() => setParams(withParams(params, { min_rating: undefined, min_price: undefined, max_price: undefined, in_stock: undefined, min_reviews: undefined }))}>Limpar filtros</button>}
                {cats.data?.slice(0, 5).map((c) => (<Link key={c.category} to={categoryHref(c.category)} className="inline-flex h-11 items-center border border-input px-4 text-sm">{c.label}</Link>))}
              </div>
            </div>
          ) : (
            <>
              <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 xl:grid-cols-4">
                {query.data?.items.map((p) => (<li key={p.product_id}><ProductCard product={p} className="h-full" /></li>))}
              </ul>
              {query.data && (
                <Pagination className="mt-8" page={page} pageSize={query.data.page_size} total={total} onPageChange={(p) => { setParams(withParams(params, { page: p > 1 ? p : undefined })); window.scrollTo({ top: 0 }) }} />
              )}
            </>
          )}
        </div>
      </div>

      <Sheet open={sheet} onOpenChange={setSheet}>
        <SheetContent side="left" className="flex w-full max-w-sm flex-col overflow-y-auto">
          <SheetTitle>Filtros</SheetTitle>
          <div className="mt-4 flex-1">{panel}</div>
          <button type="button" onClick={() => setSheet(false)} className="btn-brand sticky bottom-0 mt-4 h-12 w-full text-sm">
            Ver {num(total)} resultados
          </button>
        </SheetContent>
      </Sheet>
    </div>
  )
}
