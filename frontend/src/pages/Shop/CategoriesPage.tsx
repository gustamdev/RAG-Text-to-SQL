import { Link } from 'react-router'
import { EmptyState, ErrorState, LoadingBlock } from '@/components/StateViews'
import { useCategories } from '@/hooks/useShop'
import { usePageTitle } from '@/hooks/usePageTitle'
import { categoryHref } from '@/lib/product'

export default function CategoriesPage() {
  usePageTitle('Categorias')
  const q = useCategories()
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 md:px-8">
      <h1 className="mb-4 text-2xl font-extrabold tracking-tight md:text-4xl">Categorias</h1>
      {q.isLoading ? <LoadingBlock /> : q.isError ? <ErrorState message={q.error.message} onRetry={() => void q.refetch()} /> : q.data?.length === 0 ? (
        <EmptyState title="Nenhuma categoria" />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {q.data?.map((c) => (
            <li key={c.category}>
              <Link to={categoryHref(c.category)} className="flex min-h-11 items-center justify-between gap-3 border border-border px-4 py-3 text-sm font-semibold hover:border-foreground">
                <span>{c.label}</span><span className="tabular-nums text-muted-foreground">{c.product_count}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
