import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { PriceBlock, QuantityStepper, StockBadge } from '@/components/product/ProductBits'
import { ProductThumb } from '@/components/product/ProductThumb'
import { RatingStars } from '@/components/product/RatingStars'
import { ShippingCalculator } from '@/components/product/ShippingCalculator'
import { Specs } from '@/components/product/Specs'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useCartActions, useProduct } from '@/hooks/useShop'
import { ApiError } from '@/services/http'
import { catalogApi } from '@/services/shop'
import { measure, num, weight } from '@/lib/format'
import { categoryHref, money } from '@/lib/product'
import { notify, notifyApiError } from '@/lib/notify'

function Skeleton() {
  return (
    <div className="mx-auto grid max-w-[1600px] gap-8 px-4 py-6 md:grid-cols-2 md:px-8" aria-busy="true">
      <div className="aspect-square animate-pulse bg-muted motion-reduce:animate-none" />
      <div className="space-y-4">
        {[3 / 4, 1 / 3, 1 / 4, 1 / 2].map((w) => (<div key={w} style={{ width: `${w * 100}%` }} className="h-8 animate-pulse bg-muted motion-reduce:animate-none" />))}
      </div>
    </div>
  )
}

export default function ProductPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const query = useProduct(id)
  const { add } = useCartActions()
  const [qty, setQty] = useState(1)
  const p = query.data
  usePageTitle(p?.title ?? 'Produto')

  if (query.isLoading) return <Skeleton />
  if (query.error instanceof ApiError && query.error.status === 404)
    return <div className="mx-auto max-w-[1600px] px-4 py-10 md:px-8"><EmptyState title="Produto não encontrado" actionTo="/" actionLabel="Ir para o início" /></div>
  if (!p) return <div className="mx-auto max-w-[1600px] px-4 py-10 md:px-8"><ErrorState message={query.error?.message} onRetry={() => void query.refetch()} /></div>

  const out = p.stock < 1
  const addToCart = async (go: boolean) => {
    try {
      await add.mutateAsync({ id: p.product_id, qty })
      if (go) navigate('/checkout')
      else notify.success('Adicionado ao carrinho', { id: 'cart-added', action: { label: 'Ver carrinho', onClick: () => navigate('/carrinho') } })
    } catch (e) {
      notifyApiError(e, { fallback: 'Não foi possível adicionar.', retry: () => void addToCart(go) })
    }
  }
  const dist = p.rating_distribution
  const distTotal = dist ? Object.values(dist).reduce((a, b) => a + b, 0) : 0

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-6 pb-24 md:px-8 md:pb-10">
      <nav aria-label="Trilha" className="mb-4 text-xs text-muted-foreground">
        <Link to="/" className="hover:underline">Início</Link> / <Link to={categoryHref(p.category)} className="hover:underline">{p.category_label}</Link>
      </nav>

      <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section aria-label="Imagens do produto">
          <ProductThumb imageUrl={p.image_url} alt={p.title} className="aspect-square border border-border" />
        </section>

        <section aria-label="Comprar" className="space-y-5">
          <div>
            <Link to={categoryHref(p.category)} className="text-sm font-semibold underline underline-offset-4">{p.category_label}</Link>
            <h1 className="mt-1 text-2xl font-extrabold leading-tight tracking-tight md:text-[28px]">{p.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <RatingStars value={p.avg_rating} count={p.review_count} />
              <span className="text-xs text-muted-foreground">{num(p.units_sold)} vendidos</span>
            </div>
          </div>
          <PriceBlock cents={p.price_cents} large />
          <div className="flex items-center gap-4">
            <StockBadge stock={p.stock} />
            {!out && <QuantityStepper value={qty} max={p.stock} label={p.title} onChange={setQty} />}
          </div>
          <div className="hidden flex-col gap-2 md:flex">
            <button type="button" disabled={out || add.isPending} aria-busy={add.isPending} onClick={() => void addToCart(false)} className="btn-brand h-12 text-sm disabled:opacity-50">Adicionar ao carrinho</button>
            <button type="button" disabled={out || add.isPending} onClick={() => void addToCart(true)} className="h-12 border border-foreground text-sm font-bold disabled:opacity-50">Comprar agora</button>
          </div>
          <ShippingCalculator id="pdp" fetcher={(zip) => catalogApi.freight(p.product_id, zip)} />
        </section>
      </div>

      <div className="mt-10 grid gap-10 md:grid-cols-2">
        <section aria-labelledby="specs">
          <h2 id="specs" className="mb-3 text-xl font-extrabold tracking-tight">Especificações</h2>
          <Specs items={[['Peso', weight(p.weight_g)], ['Comprimento', measure(p.length_cm, 'cm')], ['Altura', measure(p.height_cm, 'cm')], ['Largura', measure(p.width_cm, 'cm')]]} />
        </section>
        <section aria-labelledby="reviews">
          <h2 id="reviews" className="mb-3 text-xl font-extrabold tracking-tight">Avaliações</h2>
          <RatingStars value={p.avg_rating} count={p.review_count} />
          {dist && distTotal > 0 && (
            <ul className="mt-3 space-y-1.5">
              {[5, 4, 3, 2, 1].map((n) => {
                const c = dist[String(n)] ?? 0
                return (
                  <li key={n} className="flex items-center gap-2 text-xs tabular-nums">
                    <span className="w-14">{n} estrelas</span>
                    <span className="h-2 flex-1 bg-muted" aria-hidden="true"><span className="block h-full bg-foreground" style={{ width: `${(c / distTotal) * 100}%` }} /></span>
                    <span className="w-10 text-right text-muted-foreground">{c}</span>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>

      <div className="fixed inset-x-0 bottom-14 z-20 flex items-center gap-3 border-t border-border bg-background p-3 md:hidden">
        <p className="text-lg font-extrabold tabular-nums">{money(p.price_cents)}</p>
        <button type="button" disabled={out || add.isPending} onClick={() => void addToCart(false)} className="btn-brand h-12 flex-1 text-sm disabled:opacity-50">
          {out ? 'Esgotado' : 'Adicionar ao carrinho'}
        </button>
      </div>
    </div>
  )
}
