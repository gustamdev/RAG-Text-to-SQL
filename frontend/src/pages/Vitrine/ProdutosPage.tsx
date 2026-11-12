import { Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { Pagination } from '@/components/product/Pagination'
import { ProductCard, ProductCardSkeleton } from '@/components/product/ProductCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useCategories, useProducts } from '@/hooks/useProducts'
import { num } from '@/lib/format'
import { categoryLabel } from '@/lib/product'
import { enumParam, intParam, withParams } from '@/lib/searchParams'
import type { ProductSort } from '@/types/product'

const PAGE_SIZE = 24
const SORTS: ReadonlyArray<{ value: ProductSort; label: string }> = [
  { value: 'units', label: 'Mais vendidos' },
  { value: 'rating', label: 'Melhor avaliados' },
  { value: 'price_asc', label: 'Menor preço' },
  { value: 'price_desc', label: 'Maior preço' },
]
const SORT_VALUES = SORTS.map((s) => s.value)

export default function ProdutosPage() {
  usePageTitle('Catálogo')
  const [params, setParams] = useSearchParams()

  const q = params.get('q') ?? ''
  const category = params.get('category') ?? ''
  const sort = enumParam(params, 'sort', SORT_VALUES, 'units')
  const page = intParam(params, 'page', 1)

  // O texto digitado é local; a URL (e a busca) só mudam depois de uma pausa na digitação.
  const [search, setSearch] = useState(q)
  const debouncedSearch = useDebouncedValue(search.trim())
  const pushedQ = useRef(q)
  useEffect(() => {
    if (debouncedSearch === pushedQ.current) return
    pushedQ.current = debouncedSearch
    setParams((current) => withParams(current, { q: debouncedSearch, page: undefined }), { replace: true })
  }, [debouncedSearch, setParams])

  // Botão voltar/avançar (ou "Limpar") muda ?q= por fora: sincroniza o campo, sem brigar com a digitação.
  useEffect(() => {
    if (q === pushedQ.current) return
    pushedQ.current = q
    setSearch(q)
  }, [q])

  const categories = useCategories()
  const products = useProducts({
    ...(q ? { q } : {}),
    ...(category ? { category } : {}),
    sort,
    page,
    page_size: PAGE_SIZE,
  })

  const hasFilters = q !== '' || category !== ''
  const data = products.data

  function update(changes: Record<string, string | number | undefined>) {
    setParams((current) => withParams(current, { page: undefined, ...changes }))
  }

  function goToPage(next: number) {
    setParams((current) => withParams(current, { page: next > 1 ? next : undefined }))
    window.scrollTo({ top: 0 })
  }

  function clearFilters() {
    setSearch('')
    setParams((current) => withParams(current, { q: undefined, category: undefined, page: undefined }))
  }

  return (
    <>
      <PageHeader
        eyebrow="Catálogo"
        title="Produtos"
        description="Preço médio, nota e volume de vendas de cada produto da Olist."
      />

      <div className="mx-auto max-w-[1600px] px-4 py-8 md:px-8 md:py-10">
        <form
          role="search"
          onSubmit={(e) => e.preventDefault()}
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[2fr_1.2fr_1fr_auto] lg:items-end"
        >
          <div className="sm:col-span-2 lg:col-span-1">
            <Label htmlFor="q" className="eyebrow">
              Buscar
            </Label>
            <div className="relative mt-2">
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
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
            <Select
              id="category"
              className="mt-2 h-11"
              value={category}
              onChange={(e) => update({ category: e.target.value })}
            >
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
            <Label htmlFor="sort" className="eyebrow">
              Ordenar por
            </Label>
            <Select id="sort" className="mt-2 h-11" value={sort} onChange={(e) => update({ sort: e.target.value })}>
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
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

        <p className="mt-8 text-sm text-muted-foreground" aria-live="polite">
          {data ? `${num(data.total)} ${data.total === 1 ? 'produto' : 'produtos'}` : ' '}
        </p>

        <div className="mt-4">
          {products.isError ? (
            <ErrorState message={products.error.message} onRetry={() => products.refetch()} />
          ) : products.isPending ? (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-4 xl:grid-cols-6">
              {Array.from({ length: 12 }, (_, i) => (
                <ProductCardSkeleton key={i} />
              ))}
            </div>
          ) : data && data.total === 0 ? (
            <EmptyState title="Nenhum produto encontrado" text="Tente outro termo ou remova os filtros." />
          ) : (
            data && (
              <div
                className={`grid grid-cols-2 gap-3 transition-opacity md:grid-cols-3 md:gap-4 lg:grid-cols-4 xl:grid-cols-6 ${
                  products.isPlaceholderData ? 'opacity-50' : ''
                }`}
              >
                {data.items.map((p) => (
                  <ProductCard key={p.product_id} product={p} />
                ))}
              </div>
            )
          )}
        </div>

        {data && data.total > 0 && (
          <Pagination
            className="mt-10"
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPageChange={goToPage}
          />
        )}
      </div>
    </>
  )
}
