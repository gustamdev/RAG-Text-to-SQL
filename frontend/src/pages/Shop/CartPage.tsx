import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router'
import { useCustomer } from '@/app/customer-context'
import { QuantityStepper } from '@/components/product/ProductBits'
import { ProductThumb } from '@/components/product/ProductThumb'
import { ShippingCalculator } from '@/components/product/ShippingCalculator'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useCart, useCartActions, useCategories } from '@/hooks/useShop'
import { notify, notifyApiError } from '@/lib/notify'
import { categoryHref, money, productHref } from '@/lib/product'
import { cartApi } from '@/services/shop'
import type { CartLine } from '@/types/shop'

const WARNING: Record<NonNullable<CartLine['warning']>, string> = {
  stock_reduced: 'A quantidade foi ajustada ao estoque disponível.',
  out_of_stock: 'Este item está esgotado. Remova para continuar.',
  price_changed: 'O preço mudou desde que você adicionou.',
}

export default function CartPage() {
  usePageTitle('Carrinho')
  const navigate = useNavigate()
  const { customer } = useCustomer()
  const { cart, isLoading, isError, refetch } = useCart()
  const { add, setQty, ack, remove } = useCartActions()
  const cats = useCategories()
  const fail = (e: unknown) => notifyApiError(e, { fallback: 'Não foi possível atualizar o carrinho.' })
  // Os avisos por item continuam na linha (com "Confirmar e manter"); o aviso global só chama a atenção.
  const adjusted = cart.items.some((l) => l.warning === 'stock_reduced')
  useEffect(() => {
    if (adjusted) notify.warning('Ajustamos a quantidade de itens ao estoque. Confira o carrinho.', { id: 'cart-adjusted' })
  }, [adjusted])

  // Desfazer = adicionar de volta a mesma quantidade.
  const undo = (l: CartLine) => add.mutateAsync({ id: l.product_id, qty: l.qty }).catch(fail)
  const onRemove = (l: CartLine) =>
    remove.mutate(l.product_id, {
      onError: fail,
      onSuccess: () => notify.info('Item removido', { id: `cart-removed:${l.product_id}`, action: { label: 'Desfazer', onClick: () => void undo(l) } }),
    })

  const checkout = () => navigate(customer ? '/checkout' : `/entrar?redirect=${encodeURIComponent('/checkout')}`)

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-6 pb-32 md:px-8 md:pb-10">
      <h1 className="mb-6 text-2xl font-extrabold tracking-tight md:text-4xl">Carrinho{cart.item_count > 0 && ` (${cart.item_count} ${cart.item_count === 1 ? 'item' : 'itens'})`}</h1>
      {isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : isLoading ? (
        <div role="status" aria-busy="true" className="h-48 animate-pulse bg-muted motion-reduce:animate-none"><span className="sr-only">Carregando carrinho…</span></div>
      ) : cart.items.length === 0 ? (
        <div>
          <EmptyState title="Seu carrinho está vazio" text="Veja o que está em alta." actionTo="/busca?sort=best_selling" actionLabel="Continuar comprando" />
          <div className="mt-4 flex flex-wrap gap-2">
            {cats.data?.slice(0, 6).map((c) => (<Link key={c.category} to={categoryHref(c.category)} className="inline-flex h-11 items-center border border-input px-4 text-sm">{c.label}</Link>))}
          </div>
        </div>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
          <ul className="divide-y divide-border border-y border-border">
            {cart.items.map((l) => (
              <li key={l.product_id} className="flex gap-3 py-4">
                <ProductThumb className="size-20 shrink-0 border border-border md:size-24" />
                <div className="min-w-0 flex-1">
                  <Link to={productHref(l.product_id)} className="line-clamp-2 text-sm font-semibold hover:underline">{l.title}</Link>
                  <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">{money(l.unit_price_cents)} cada{l.stock > 0 && l.stock <= 5 && ` · Restam ${l.stock}`}</p>
                  {l.warning && (
                    <div role="alert" className="mt-2 border border-brand px-3 py-2 text-sm">
                      <p className="font-semibold text-brand">{WARNING[l.warning]}</p>
                      {l.warning !== 'out_of_stock' && (
                        <button type="button" onClick={() => ack.mutate(l.product_id, { onError: fail })} className="mt-1 text-xs font-bold underline">Confirmar e manter</button>
                      )}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-4">
                    {l.warning !== 'out_of_stock' && (
                      <QuantityStepper value={l.qty} max={l.stock} label={l.title} onChange={(qty) => setQty.mutate({ id: l.product_id, qty }, { onError: fail })} />
                    )}
                    <button type="button" onClick={() => onRemove(l)} className="min-h-11 text-sm font-semibold underline md:min-h-0">
                      Remover<span className="sr-only"> {l.title}</span>
                    </button>
                  </div>
                </div>
                <p className="shrink-0 text-base font-extrabold tabular-nums">{money(l.line_total_cents)}</p>
              </li>
            ))}
          </ul>

          <aside aria-label="Resumo" className="h-fit space-y-5 border border-border p-5 lg:sticky lg:top-40">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt>Subtotal</dt><dd className="font-bold tabular-nums">{money(cart.subtotal_cents)}</dd></div>
              <div className="flex justify-between text-muted-foreground"><dt>Frete</dt><dd>calculado no checkout</dd></div>
            </dl>
            {customer && <ShippingCalculator id="cart" fetcher={(zip) => cartApi.freight({ zip })} />}
            <p className="text-xs text-muted-foreground">Valores estimados: o servidor recalcula tudo ao finalizar. Pagamento simulado.</p>
            {cart.blocked && <p role="alert" className="text-sm font-semibold text-destructive">Resolva os avisos dos itens para finalizar.</p>}
            <div className="fixed inset-x-0 bottom-14 z-20 border-t border-border bg-background p-3 lg:static lg:border-0 lg:p-0">
              <button type="button" disabled={cart.blocked} onClick={checkout} className="btn-brand h-12 w-full text-sm disabled:opacity-50">
                Finalizar compra · {money(cart.subtotal_cents)}
              </button>
            </div>
            {!customer && <p className="text-xs text-muted-foreground">Para finalizar, entre ou crie uma conta. Seu carrinho será mantido.</p>}
          </aside>
        </div>
      )}
    </div>
  )
}
