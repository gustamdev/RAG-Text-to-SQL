import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { EmptyState, ErrorState, InlineError, LoadingBlock } from '@/components/StateViews'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useAddresses, useCards, useCart } from '@/hooks/useShop'
import { notify, notifyApiError } from '@/lib/notify'
import { cartSignature, clearOpenOrder, isStale, keepKeyAfter, loadOpenOrder, saveOpenOrder } from '@/lib/openOrder'
import { AddressForm } from '@/components/AddressForm'
import { CardFields } from '@/components/CardForm'
import { EMPTY_CARD, MAX_CARDS, cardIssue, cvvOk, fmtExp, isExpired, toCardInput, type CardIssue, type CardValue } from '@/lib/cards'
import { maskZip, money, newIdempotencyKey } from '@/lib/product'
import { cn } from '@/lib/utils'
import { ApiError } from '@/services/http'
import { accountApi, cartApi, checkoutApi } from '@/services/shop'
import type { FreightCode, Order, PayInput } from '@/types/shop'

const STEPS = ['endereco', 'frete', 'pagamento', 'revisao'] as const
type Step = (typeof STEPS)[number]
const STEP_LABEL: Record<Step, string> = { endereco: 'Endereço', frete: 'Frete', pagamento: 'Pagamento', revisao: 'Revisão' }
const field = 'mt-1 h-11 w-full border border-input px-3 text-base md:text-sm'
const option = 'flex min-h-14 cursor-pointer items-center gap-3 border border-border p-4 text-sm has-[:checked]:border-2 has-[:checked]:border-foreground has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foreground'

export default function CheckoutPage() {
  usePageTitle('Checkout')
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { cart, isLoading: cartLoading } = useCart()
  const addresses = useAddresses()
  // Pedido aberto guardado (reload ou "Pagar" no pedido): retoma direto no pagamento.
  const [resume] = useState(loadOpenOrder)
  const [step, setStep] = useState<Step>(resume ? 'pagamento' : 'endereco')
  const [addressId, setAddressId] = useState<string | undefined>(resume?.addressId)
  const [shipping, setShipping] = useState<FreightCode | undefined>(resume?.shipping)
  const [adding, setAdding] = useState(false)
  const cards = useCards()
  const saved = cards.data ?? []
  const [card, setCard] = useState<CardValue>(EMPTY_CARD)
  // undefined = primeiro cartão salvo válido (ou novo, se não houver); 'new' = cartão novo. Vencido nunca é selecionável.
  const [choice, setChoice] = useState<string>()
  const [savedCvv, setSavedCvv] = useState('')
  // Salvar é opt-in: só bandeira, final e validade vão para a conta.
  const [saveCard, setSaveCard] = useState(false)
  const now = new Date()
  const usable = saved.filter((c) => !isExpired(c, now))
  const savedSel = choice === 'new' ? undefined : usable.find((c) => c.id === choice) ?? usable[0]
  const canSave = saved.length < MAX_CARDS
  const [cardError, setCardError] = useState<CardIssue>()
  const [busy, setBusy] = useState(false)
  // Uma Idempotency-Key por operação; reaproveitada em retry (timeout/rede) e trocada após recusa.
  const body = useRef<HTMLDivElement>(null)
  const firstStep = useRef(true)
  const createKey = useRef(newIdempotencyKey())
  const payKey = useRef(newIdempotencyKey())

  // Troca de etapa: foco no título da etapa (leitor de tela anuncia a mudança).
  useEffect(() => {
    if (firstStep.current) { firstStep.current = false; return }
    const h = body.current?.querySelector('h2')
    h?.setAttribute('tabindex', '-1')
    h?.focus()
  }, [step])

  const selected = addresses.data?.find((a) => a.id === addressId)
  const freight = useQuery({
    queryKey: ['account', 'freight', addressId],
    queryFn: () => cartApi.freight({ address_id: addressId! }),
    enabled: !!addressId && step !== 'endereco',
  })
  const chosen = freight.data?.options.find((o) => o.code === shipping)
  const total = cart.subtotal_cents + (chosen?.price_cents ?? 0)
  const last4 = savedSel?.last4 ?? card.number.replace(/\D/g, '').slice(-4)

  if (cartLoading || addresses.isLoading) return <LoadingBlock />
  if (cart.items.length === 0) return <div className="mx-auto max-w-3xl px-4 py-10"><EmptyState title="Seu carrinho está vazio" actionTo="/" actionLabel="Continuar comprando" /></div>
  if (cart.blocked) return <div className="mx-auto max-w-3xl px-4 py-10"><EmptyState title="Revise seu carrinho" text="Há itens com aviso de estoque ou preço." actionTo="/carrinho" actionLabel="Voltar ao carrinho" /></div>
  if (addresses.isError) return <div className="mx-auto max-w-3xl px-4 py-10"><ErrorState onRetry={() => void addresses.refetch()} /></div>

  const confirm = async () => {
    if (!addressId || !shipping) return
    setBusy(true)
    const sig = cartSignature(cart.items)
    try {
      let o = loadOpenOrder()
      if (o && isStale(o, addressId, shipping, sig)) {
        try {
          await accountApi.cancel(o.id)
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            clearOpenOrder()
            notify.error('Esse pedido já foi pago ou fechado e não pode ser trocado.', { id: 'checkout-closed', action: toOrders })
            return
          }
          if (!(e instanceof ApiError && e.status === 404)) throw e
        }
        clearOpenOrder()
        o = null
        createKey.current = newIdempotencyKey()
        payKey.current = newIdempotencyKey()
      }
      if (!o) {
        try {
          const created: Order = await checkoutApi.create(addressId, shipping, createKey.current)
          o = { id: created.order_id, addressId, shipping, cartSig: sig }
          saveOpenOrder(o)
        } catch (e) {
          if (!keepKeyAfter(e)) createKey.current = newIdempotencyKey()
          throw e
        }
      }
      let res
      try {
        res = await checkoutApi.pay(o.id, payBody(), payKey.current)
      } catch (e) {
        if (!keepKeyAfter(e)) payKey.current = newIdempotencyKey()
        throw e
      }
      if (res.payment.status === 'refused') {
        payKey.current = newIdempotencyKey()
        // Número e CVV não ficam na memória depois de recusa; o cliente digita de novo.
        setCard(EMPTY_CARD)
        setSavedCvv('')
        notify.warning('Pagamento recusado. Confira o cartão ou tente outro.', { id: 'payment-refused', action: { label: 'Tentar outro cartão', onClick: otherCard } })
        setStep('pagamento')
        return
      }
      clearOpenOrder()
      setCard(EMPTY_CARD)
      setSavedCvv('')
      void qc.invalidateQueries({ queryKey: ['cart'] })
      void qc.invalidateQueries({ queryKey: ['account', 'cards'] })
      notify.success(`Pagamento aprovado. Pedido #${o.id.slice(0, 6).toUpperCase()} criado.`, { id: 'payment-approved' })
      navigate(`/pedido/${o.id}/confirmacao`, { replace: true })
    } catch (e) {
      const conflict = e instanceof ApiError && e.status === 409
      if (e instanceof ApiError && e.status === 504) notify.error('Não conseguimos confirmar o pagamento.', { id: 'payment-timeout', action: { label: 'Tentar de novo', onClick: () => void confirm() } })
      else if (conflict && /estoque/i.test(e.message)) notify.error(e.message, { id: 'checkout-stock', action: { label: 'Ir ao carrinho', onClick: () => navigate('/carrinho') } })
      else if (conflict && /em aberto/i.test(e.message)) notify.error(e.message, { id: 'checkout-open', action: toOrders })
      else if (conflict && /Limite de tentativas/i.test(e.message)) notify.error(`${e.message} Cancele este pedido para começar de novo.`, { id: 'payment-limit', action: toOrders, duration: 12000 })
      else if (conflict && /Reserva expirada/i.test(e.message)) notify.warning(e.message, { id: 'reservation-expired', action: { label: 'Ver carrinho', onClick: () => navigate('/carrinho') } })
      else notifyApiError(e, { fallback: 'Não foi possível concluir.', retry: () => void confirm() })
      if (conflict && /Limite de tentativas/i.test(e.message)) {
        // Pedido sem tentativas: cancele-o em Meus pedidos (ou espere a reserva vencer) e finalize de novo.
        clearOpenOrder()
        createKey.current = newIdempotencyKey()
        payKey.current = newIdempotencyKey()
      }
      // Pedido guardado já cancelado/expirado pelo servidor (409 transição inválida ou 404): recomeça do zero.
      if (e instanceof ApiError && (e.status === 404 || (e.status === 409 && /não é permitida/i.test(e.message)))) {
        clearOpenOrder()
        createKey.current = newIdempotencyKey()
        payKey.current = newIdempotencyKey()
      }
      if (e instanceof ApiError && e.status === 409 && /Reserva expirada/i.test(e.message)) {
        clearOpenOrder()
        createKey.current = newIdempotencyKey()
        payKey.current = newIdempotencyKey()
      }
    } finally {
      setBusy(false)
    }
  }

  const toOrders = { label: 'Meus pedidos', onClick: () => navigate('/conta/pedidos') }
  // Recusa: volta ao pagamento com os campos do cartão vazios e o foco no número.
  const otherCard = () => {
    setCard(EMPTY_CARD)
    setSavedCvv('')
    setChoice('new')
    requestAnimationFrame(() => document.getElementById('c-num')?.focus())
  }
  const payBody = (): PayInput =>
    savedSel ? { saved_card_id: savedSel.id, cvv: savedCvv } : { ...toCardInput(card), save_card: canSave && saveCard }

  const goCard = (e: FormEvent) => {
    e.preventDefault()
    const err = savedSel ? (cvvOk(savedCvv) ? undefined : { field: 'cvv' as const, message: 'Informe o CVV do cartão.' }) : cardIssue(card)
    if (err) return setCardError(err)
    setCardError(undefined)
    setStep('revisao')
  }
  const idx = STEPS.indexOf(step)
  const btn = 'btn-brand h-12 px-8 text-sm disabled:opacity-50'

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 md:px-8">
      <h1 className="sr-only">Finalizar compra</h1>
      <ol className="mb-6 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {STEPS.map((s, i) => (
          <li key={s} aria-current={i === idx ? 'step' : undefined} className={cn(i === idx ? 'font-extrabold' : 'text-muted-foreground')}>
            {i < idx ? <button type="button" onClick={() => setStep(s)} className="underline">{i + 1} {STEP_LABEL[s]}</button> : <span>{i + 1} {STEP_LABEL[s]}</span>}
          </li>
        ))}
      </ol>
      <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
        <div ref={body}>
          {step === 'endereco' && (
            <section aria-labelledby="h-end">
              <h2 id="h-end" className="mb-3 text-xl font-extrabold">Endereço de entrega</h2>
              {!(adding || addresses.data?.length === 0) && (
                <fieldset className="space-y-2">
                  <legend className="sr-only">Escolha um endereço</legend>
                  {addresses.data?.map((a) => (
                    <label key={a.id} className="flex min-h-14 cursor-pointer items-start gap-3 border border-border p-4 text-sm has-[:checked]:border-2 has-[:checked]:border-foreground has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foreground">
                      <input type="radio" name="addr" checked={addressId === a.id} onChange={() => setAddressId(a.id)} className="mt-1 size-4 accent-foreground" />
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-2"><strong>{a.label}</strong>{a.is_default && <span className="border border-foreground px-1.5 text-xs font-bold uppercase tracking-wide">Padrão</span>}</span>
                        <span className="block">{a.recipient}</span>
                        <span className="block text-muted-foreground">{a.street}, {a.number}{a.complement && ` · ${a.complement}`}<br />{a.district} · {a.city}/{a.state} · {maskZip(a.zip)}</span>
                      </span>
                    </label>
                  ))}
                </fieldset>
              )}
              {(adding || addresses.data?.length === 0) ? (
                <div className="mt-4"><AddressForm firstAddress={addresses.data?.length === 0} onCancel={() => setAdding(false)} onSaved={(id) => { setAddressId(id); setAdding(false) }} /></div>
              ) : (addresses.data?.length ?? 0) < 3 && (
                <button type="button" onClick={() => setAdding(true)} className="mt-3 min-h-11 border border-input px-4 text-sm font-bold">+ Adicionar novo endereço</button>
              )}
              <div className="mt-6" hidden={adding || addresses.data?.length === 0}><button type="button" disabled={!addressId} onClick={() => setStep('frete')} className={btn}>Continuar</button></div>
            </section>
          )}

          {step === 'frete' && (
            <section aria-labelledby="h-fr">
              <h2 id="h-fr" className="mb-3 text-xl font-extrabold">Frete</h2>
              {freight.isLoading ? <LoadingBlock label="Calculando frete…" /> : freight.isError ? <ErrorState message={freight.error.message} onRetry={() => void freight.refetch()} /> : (
                <fieldset className="space-y-2">
                  <legend className="sr-only">Opção de frete</legend>
                  {freight.data?.options.map((o) => (
                    <label key={o.code} className="flex cursor-pointer items-center justify-between gap-3 border border-border p-3 text-sm has-[:checked]:border-foreground">
                      <span className="flex items-center gap-3"><input type="radio" name="ship" checked={shipping === o.code} onChange={() => setShipping(o.code)} /><span><strong>{o.label}</strong><br />{o.days_min} a {o.days_max} dias úteis</span></span>
                      <span className="font-bold tabular-nums">{money(o.price_cents)}</span>
                    </label>
                  ))}
                </fieldset>
              )}
              <div className="mt-6"><button type="button" disabled={!shipping} onClick={() => setStep('pagamento')} className={btn}>Continuar</button></div>
            </section>
          )}

          {step === 'pagamento' && (
            <form onSubmit={goCard} noValidate aria-labelledby="h-pg">
              <h2 id="h-pg" className="mb-3 text-xl font-extrabold">Pagamento (simulado)</h2>
              <p className="mb-4 border border-border bg-surface p-3 text-sm">
                Nenhum valor será cobrado. Cartões de teste: final <strong>0001</strong> aprova, <strong>0002</strong> recusa, <strong>0003</strong> simula timeout. Ex.: 4242 4242 4242 0001.
              </p>
              {cards.isLoading ? <LoadingBlock /> : (
                <>
                  {saved.length > 0 && (
                    <fieldset className="mb-4 space-y-2">
                      <legend className="sr-only">Forma de pagamento</legend>
                      {saved.map((c) => {
                        const expired = isExpired(c, now)
                        return (
                        <div key={c.id}>
                          <label className={cn(option, expired && 'cursor-not-allowed opacity-60')}>
                            <input type="radio" name="pay" disabled={expired} checked={savedSel?.id === c.id} onChange={() => { setChoice(c.id); setCardError(undefined) }} className="size-4 accent-foreground" />
                            <span><strong className="capitalize">{c.brand}</strong> •••• {c.last4} <span className="text-muted-foreground">· {expired ? 'vencido' : 'validade'} {fmtExp(c)}</span></span>
                          </label>
                          {savedSel?.id === c.id && (
                            <div className="mt-2 max-w-40"><label htmlFor="c-scvv" className="text-sm font-semibold">CVV</label>
                              <input id="c-scvv" {...(cardError ? { 'aria-invalid': true, 'aria-describedby': 'c-err' } : {})} inputMode="numeric" autoComplete="cc-csc" maxLength={4} value={savedCvv} onChange={(e) => setSavedCvv(e.target.value.replace(/\D/g, '').slice(0, 4))} className={field} /></div>
                          )}
                        </div>
                        )
                      })}
                      <label className={option}>
                        <input type="radio" name="pay" checked={!savedSel} onChange={() => { setChoice('new'); setCardError(undefined) }} className="size-4 accent-foreground" />
                        Usar um novo cartão
                      </label>
                    </fieldset>
                  )}
                  {!savedSel && (
                    <>
                      <CardFields value={card} onChange={setCard} issue={cardError} />
                      {canSave ? (
                        <label className="mt-3 flex min-h-11 items-start gap-2 text-sm">
                          <input type="checkbox" checked={saveCard} onChange={(e) => setSaveCard(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-foreground md:size-4" />
                          <span>Salvar este cartão para a próxima compra <span className="text-muted-foreground">(guardamos só bandeira, final e validade; nunca o número completo, o CVV ou o nome)</span></span>
                        </label>
                      ) : <p className="mt-3 text-sm text-muted-foreground">Limite de {MAX_CARDS} cartões salvos atingido. Este cartão não será salvo.</p>}
                    </>
                  )}
                </>
              )}
              {cardError && <InlineError id="c-err">{cardError.message}</InlineError>}
              <div className="mt-6"><button disabled={cards.isLoading} className={btn}>Continuar</button></div>
            </form>
          )}

          {step === 'revisao' && (
            <section aria-labelledby="h-rv">
              <h2 id="h-rv" className="mb-3 text-xl font-extrabold">Revisão</h2>
              <dl className="divide-y divide-border border-y border-border text-sm">
                <div className="flex justify-between gap-4 py-3"><dt>Entrega</dt><dd className="text-right">{selected && `${selected.street}, ${selected.number} - ${selected.city}/${selected.state}`}</dd></div>
                <div className="flex justify-between gap-4 py-3"><dt>Frete</dt><dd>{chosen && `${chosen.label}, ${chosen.days_min} a ${chosen.days_max} dias úteis`}</dd></div>
                <div className="flex justify-between gap-4 py-3"><dt>Cartão</dt><dd>{savedSel && <span className="capitalize">{savedSel.brand} </span>}•••• {last4} (simulado)</dd></div>
              </dl>
              <p className="mt-3 text-sm text-muted-foreground">Nenhum valor será cobrado. Pagamento simulado.</p>
              <div className="mt-6"><button type="button" disabled={busy} aria-busy={busy} onClick={() => void confirm()} className={btn}>{busy ? 'Confirmando…' : `Confirmar pedido · ${money(total)}`}</button></div>
            </section>
          )}
        </div>

        <aside aria-label="Resumo do pedido" className="h-fit border border-border p-5 text-sm">
          <ul className="space-y-2">
            {cart.items.map((l) => (<li key={l.product_id} className="flex justify-between gap-3"><span className="line-clamp-1">{l.qty}× {l.title}</span><span className="tabular-nums">{money(l.line_total_cents)}</span></li>))}
          </ul>
          <dl className="mt-4 space-y-1 border-t border-border pt-3">
            <div className="flex justify-between"><dt>Subtotal</dt><dd className="tabular-nums">{money(cart.subtotal_cents)}</dd></div>
            <div className="flex justify-between"><dt>Frete</dt><dd className="tabular-nums">{chosen ? money(chosen.price_cents) : '—'}</dd></div>
            <div className="flex justify-between text-base font-extrabold"><dt>Total</dt><dd className="tabular-nums">{money(total)}</dd></div>
          </dl>
        </aside>
      </div>
    </div>
  )
}
