import { createElement } from 'react'
import { Link } from 'react-router'
import { ProductShelf } from '@/components/product/ProductShelf'
import { ErrorState } from '@/components/StateViews'
import { useCategories, useProducts } from '@/hooks/useShop'
import { usePageTitle } from '@/hooks/usePageTitle'
import { categoryIcon } from '@/lib/categoryIcons'
import { categoryHref } from '@/lib/product'

function Showcase({ category, label }: { category: string; label: string }) {
  const q = useProducts({ category, sort: 'best_selling', page_size: 12 })
  return (
    <ProductShelf title={label} href={categoryHref(category)} products={q.data?.items} loading={q.isLoading} error={q.isError} onRetry={() => void q.refetch()} />
  )
}

export default function HomePage() {
  usePageTitle('')
  const cats = useCategories()
  const best = useProducts({ sort: 'best_selling', page_size: 12 })
  const rated = useProducts({ sort: 'rating', min_rating: 4.5, min_reviews: 20, page_size: 12 })
  const top = cats.data?.slice(0, 12) ?? []

  return (
    <div className="mx-auto max-w-[1600px] px-4 md:px-8">
      <section aria-label="Destaque" className="mt-4 grid gap-px border border-border bg-border md:grid-cols-[2fr_1fr]">
        <div className="flex flex-col justify-between gap-10 bg-foreground p-6 text-background md:min-h-72 md:p-10">
          <h1 className="display text-4xl md:text-6xl">Tudo para a casa, do jeito que cabe no bolso.</h1>
          <div className="flex flex-wrap items-center gap-4">
            <Link to="/busca?sort=best_selling" className="btn-brand inline-flex h-11 items-center px-6 text-sm">Ver os mais vendidos</Link>
            <p className="text-xs text-background/70">Frete calculado por CEP. Pagamento simulado.</p>
          </div>
        </div>
        <ul className="grid grid-cols-3 gap-px bg-border text-sm md:grid-cols-1">
          {['Frete por CEP em cada produto', 'Parcele em 3x sem juros (simulado)', 'Cartão de teste: nada é cobrado'].map((t) => (
            <li key={t} className="flex items-center bg-background p-4 font-semibold">{t}</li>
          ))}
        </ul>
      </section>

      <section aria-label="Comprar por categoria" className="pt-8 md:pt-10">
        <h2 className="mb-4 text-xl font-extrabold tracking-tight md:text-2xl">Comprar por categoria</h2>
        {cats.isError ? (
          <ErrorState onRetry={() => void cats.refetch()} />
        ) : (
          <ul className="grid grid-cols-2 gap-px border border-border bg-border sm:grid-cols-3 lg:grid-cols-6">
            {(cats.isLoading ? Array.from({ length: 12 }, () => null) : top).map((c, i) => (
              <li key={c?.category ?? i} className="bg-background">
                {c ? (
                  <Link to={categoryHref(c.category)} className="flex h-full flex-col gap-3 p-4 hover:bg-surface focus-visible:outline-2 focus-visible:outline-ring">
                    {createElement(categoryIcon(c.category), { className: 'size-6', strokeWidth: 1.5, 'aria-hidden': true })}
                    <span className="text-sm font-semibold leading-tight">{c.label}</span>
                  </Link>
                ) : (
                  <div aria-hidden="true" className="h-24 animate-pulse bg-muted motion-reduce:animate-none" />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <ProductShelf title="Mais vendidos" href="/busca?sort=best_selling" products={best.data?.items} loading={best.isLoading} error={best.isError} onRetry={() => void best.refetch()} />
      <ProductShelf title="Melhor avaliados" href="/busca?sort=rating&min_rating=4.5&min_reviews=20" products={rated.data?.items} loading={rated.isLoading} error={rated.isError} onRetry={() => void rated.refetch()} />
      {top.slice(0, 2).map((c) => (
        <Showcase key={c.category} category={c.category} label={c.label} />
      ))}
    </div>
  )
}
