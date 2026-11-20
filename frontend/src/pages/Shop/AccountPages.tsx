import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useNavigate, useParams, useSearchParams } from 'react-router'
import { useCustomer } from '@/app/customer-context'
import { Pagination } from '@/components/product/Pagination'
import { EmptyState, ErrorState, InlineError, LoadingBlock } from '@/components/StateViews'
import { dateBR } from '@/lib/format'
import { isTransient, notify, notifyApiError } from '@/lib/notify'
import { CANCEL_REASON_LABEL, ORDER_STATE_LABEL, isCancelable, money } from '@/lib/product'
import { intParam, withParams } from '@/lib/searchParams'
import { useAddresses, useCards } from '@/hooks/useShop'
import { usePageTitle } from '@/hooks/usePageTitle'
import { CancelOrderDialog } from '@/components/CancelOrderDialog'
import { ApiError } from '@/services/http'
import { accountApi } from '@/services/shop'
import type { OrderSummary } from '@/types/shop'
import { cn } from '@/lib/utils'
import { AddressForm } from '@/components/AddressForm'
import { CardForm } from '@/components/CardForm'
import { MAX_CARDS, fmtExp, isExpired } from '@/lib/cards'

const displayName = (c: { nickname: string | null; email: string } | null) => c?.nickname || c?.email.split('@')[0] || 'Cliente'

/** Avatar redondo com a inicial do apelido (ex.: Ronaldo → R). */
function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span aria-hidden="true" className={cn('grid shrink-0 place-items-center rounded-full bg-foreground font-extrabold uppercase text-background', className)}>
      {name.trim().charAt(0)}
    </span>
  )
}

const short = (id: string) => `#${id.slice(0, 6).toUpperCase()}`

export function AccountLayout() {
  const { customer, signOut } = useCustomer()
  const link = ({ isActive }: { isActive: boolean }) => cn('block min-h-11 px-3 py-2.5 text-sm font-semibold', isActive ? 'bg-foreground text-background' : 'hover:bg-accent')
  return (
    <div className="mx-auto grid max-w-[1600px] gap-8 px-4 py-6 md:grid-cols-[240px_1fr] md:px-8">
      <aside className="space-y-4">
        <div className="flex items-center gap-3 border border-border p-4">
          <Avatar name={displayName(customer)} className="size-14 text-2xl" />
          <div className="min-w-0">
            <p className="truncate text-base font-extrabold">{displayName(customer)}</p>
            <p className="truncate text-xs text-muted-foreground">{customer?.email}</p>
          </div>
        </div>
      <nav aria-label="Conta" className="flex gap-1 md:flex-col">
        <NavLink to="/conta" end className={link}>Visão geral</NavLink>
        <NavLink to="/conta/pedidos" className={link}>Pedidos</NavLink>
        <NavLink to="/conta/enderecos" className={link}>Endereços</NavLink>
        <NavLink to="/conta/pagamentos" className={link}>Pagamentos</NavLink>
        <NavLink to="/conta/seguranca" className={link}>Segurança</NavLink>
        <button type="button" onClick={() => void signOut()} className="min-h-11 px-3 py-2.5 text-left text-sm text-muted-foreground hover:underline">Sair</button>
      </nav>
      </aside>
      <div>
        <Outlet />
      </div>
    </div>
  )
}

function ProfileForm() {
  const { customer, updateCustomer } = useCustomer()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const nickname = String(f.get('nickname') ?? '').trim()
    const phone = String(f.get('phone') ?? '').trim()
    setBusy(true)
    setError(undefined)
    try {
      const c = await accountApi.updateProfile({ ...(nickname && { nickname }), phone: phone || null })
      updateCustomer({ nickname: c.nickname, phone: c.phone })
      notify.success('Dados salvos', { id: 'profile-saved' })
    } catch (err) {
      if (isTransient(err)) { setError(undefined); notifyApiError(err) } else setError(err instanceof Error ? err.message : 'Não foi possível salvar.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={(e) => void save(e)} aria-labelledby="h-prof" className="mt-6 max-w-md space-y-3">
      <h2 id="h-prof" className="text-lg font-extrabold">Meus dados</h2>
      <div><label htmlFor="pf-nick" className="text-sm font-semibold">Nome</label><input id="pf-nick" name="nickname" defaultValue={customer?.nickname ?? ''} maxLength={40} autoComplete="nickname" className={input} /></div>
      <div><label htmlFor="pf-phone" className="text-sm font-semibold">Telefone</label><input id="pf-phone" name="phone" type="tel" defaultValue={customer?.phone ?? ''} autoComplete="tel" className={input} /></div>
      {error && <InlineError>{error}</InlineError>}
      <button disabled={busy} className="btn-brand h-11 px-6 text-sm disabled:opacity-50">Salvar</button>
    </form>
  )
}

export function AccountHome() {
  usePageTitle('Minha conta')
  const { customer } = useCustomer()
  const name = displayName(customer)
  return (
    <div>
      <h1 className="truncate text-2xl font-extrabold tracking-tight md:text-4xl">Olá, {name}!</h1>
      <ProfileForm />
    </div>
  )
}

export function OrdersPage() {
  usePageTitle('Pedidos')
  const [params, setParams] = useSearchParams()
  const page = intParam(params, 'page', 1)
  const q = useQuery({ queryKey: ['account', 'orders', page], queryFn: () => accountApi.orders(page) })
  const [filter, setFilter] = useState<'all' | 'active' | 'canceled'>('all')
  const [target, setTarget] = useState<OrderSummary | null>(null)
  const shown = q.data?.items.filter((o) => filter === 'all' || (filter === 'canceled') === (o.state === 'canceled')) ?? []
  return (
    <div>
      <h1 className="mb-4 text-2xl font-extrabold tracking-tight md:text-4xl">Pedidos</h1>
      <div role="group" aria-label="Filtrar pedidos" className="mb-3 flex gap-2">
        {([['all', 'Todos'], ['active', 'Ativos'], ['canceled', 'Cancelados']] as const).map(([k, label]) => (
          <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)} className={cn('h-11 border border-foreground px-4 text-sm font-bold', filter === k && 'bg-foreground text-background')}>{label}</button>
        ))}
      </div>
      {q.isLoading ? <LoadingBlock /> : q.isError ? <ErrorState message={q.error.message} onRetry={() => void q.refetch()} /> : q.data?.items.length === 0 ? (
        <EmptyState title="Você ainda não comprou nada" actionTo="/" actionLabel="Ver produtos" />
      ) : (
        <>
          <ul className="divide-y divide-border border-y border-border">
            {shown.map((o) => (
              <li key={o.order_id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-3 text-sm">
                <span className="font-bold">{short(o.order_id)}</span>
                <span>{dateBR(o.created_at)}</span>
                <span className={cn(o.state === 'canceled' && 'border border-foreground px-2 py-0.5 text-xs font-bold uppercase')}>{ORDER_STATE_LABEL[o.state]}{o.state === 'canceled' && o.refund_cents ? ` · reembolso ${money(o.refund_cents)}` : ''}</span>
                <span className="font-bold tabular-nums">{money(o.total_cents)}</span>
                <span className="flex items-center gap-4">
                  {isCancelable(o.state) && <button type="button" onClick={() => setTarget(o)} className="inline-flex h-11 items-center px-2 text-sm underline">Cancelar pedido<span className="sr-only"> {short(o.order_id)}</span></button>}
                  <Link to={`/conta/pedidos/${o.order_id}`} className="inline-flex h-11 items-center font-bold underline">Detalhes<span className="sr-only"> do pedido {short(o.order_id)}</span></Link>
                </span>
              </li>
            ))}
          </ul>
          {shown.length === 0 && <p className="mt-3 text-sm text-muted-foreground">Nenhum pedido nesta página.</p>}
          <CancelOrderDialog order={target} onClose={() => setTarget(null)} />
          {q.data && <Pagination className="mt-6" page={page} pageSize={q.data.page_size} total={q.data.total} onPageChange={(p) => setParams(withParams(params, { page: p > 1 ? p : undefined }))} />}
        </>
      )}
    </div>
  )
}

export function OrderView({ confirmation }: { confirmation?: boolean }) {
  const { id = '' } = useParams()
  const title = useRef<HTMLHeadingElement>(null)
  usePageTitle(confirmation ? 'Pedido recebido' : 'Pedido')
  const q = useQuery({ queryKey: ['account', 'order', id], queryFn: () => accountApi.order(id), retry: false })
  const [canceling, setCanceling] = useState(false)
  useEffect(() => { if (q.data) title.current?.focus() }, [q.data])

  if (q.isLoading) return <LoadingBlock />
  if (q.error instanceof ApiError && q.error.status === 404) return <EmptyState title="Pedido não encontrado" actionTo="/conta/pedidos" actionLabel="Meus pedidos" />
  if (!q.data) return <ErrorState message={q.error?.message} onRetry={() => void q.refetch()} />
  const o = q.data
  const a = o.address

  return (
    <div className={confirmation ? 'mx-auto max-w-[900px] px-4 py-8 md:px-8' : ''}>
      <h1 ref={title} tabIndex={-1} className="text-2xl font-extrabold tracking-tight outline-none md:text-4xl">
        {confirmation ? 'Pedido recebido' : 'Pedido'} {short(o.order_id)}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">{dateBR(o.created_at)} · {ORDER_STATE_LABEL[o.state]}</p>
      {o.state === 'canceled' && (
        <p className="mt-2 inline-block border border-foreground px-3 py-1.5 text-sm">
          <strong>Cancelado</strong>{o.canceled_at && ` em ${dateBR(o.canceled_at)}`}
          {o.cancel_reason && ` · Motivo: ${CANCEL_REASON_LABEL[o.cancel_reason]}`}
          {o.refund_cents ? ` · Reembolso de ${money(o.refund_cents)} (simulado)` : ''}
        </p>
      )}
      {confirmation && <p className="mt-2 text-sm">Previsão de entrega: {o.shipping.days_min} a {o.shipping.days_max} dias úteis ({o.shipping.label}).</p>}

      <section aria-labelledby="o-itens" className="mt-6">
        <h2 id="o-itens" className="mb-2 text-lg font-extrabold">Itens</h2>
        <ul className="divide-y divide-border border-y border-border text-sm">
          {o.items.map((i) => (<li key={i.product_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5"><span>{i.qty}× {i.title}</span><span className="flex items-center gap-4"><Link to={`/produtos/${i.product_id}`} className="font-bold underline">Ver produto<span className="sr-only">: {i.title}</span></Link><span className="tabular-nums">{money(i.line_total_cents)}</span></span></li>))}
        </ul>
        <dl className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between"><dt>Subtotal</dt><dd className="tabular-nums">{money(o.subtotal_cents)}</dd></div>
          <div className="flex justify-between"><dt>Frete</dt><dd className="tabular-nums">{money(o.freight_cents)}</dd></div>
          <div className="flex justify-between text-base font-extrabold"><dt>Total</dt><dd className="tabular-nums">{money(o.total_cents)}</dd></div>
        </dl>
      </section>

      <section aria-labelledby="o-ent" className="mt-6 text-sm">
        <h2 id="o-ent" className="mb-2 text-lg font-extrabold">Entrega e pagamento</h2>
        <p>{a.recipient}<br />{a.street}, {a.number}{a.complement && ` ${a.complement}`} - {a.district}<br />{a.city}/{a.state} · {a.zip}</p>
        {o.payment && <p className="mt-2">Cartão {o.payment.brand} •••• {o.payment.last4} (simulado)</p>}
      </section>

      <section aria-labelledby="o-tl" className="mt-6">
        <h2 id="o-tl" className="mb-2 text-lg font-extrabold">Acompanhamento</h2>
        <ol className="space-y-1 text-sm">
          {o.timeline.map((t) => (<li key={t.state + t.at}><strong>{ORDER_STATE_LABEL[t.state]}</strong> · {dateBR(t.at)}</li>))}
        </ol>
      </section>

      <div className="mt-8 flex flex-wrap gap-3">
        {confirmation && <Link to={`/conta/pedidos/${o.order_id}`} className="btn-brand inline-flex h-12 items-center px-6 text-sm">Acompanhar pedido</Link>}
        <Link to="/" className="inline-flex h-12 items-center border border-foreground px-6 text-sm font-bold">Continuar comprando</Link>
        {['created', 'refused'].includes(o.state) && <Link to="/checkout" className="btn-brand inline-flex h-12 items-center px-6 text-sm">Pagar</Link>}
        {isCancelable(o.state) && <button type="button" onClick={() => setCanceling(true)} className="h-12 px-6 text-sm font-bold underline">Cancelar pedido</button>}
      </div>
      <CancelOrderDialog order={canceling ? o : null} onClose={() => setCanceling(false)} />
    </div>
  )
}

export function AddressesPage() {
  usePageTitle('Endereços')
  const qc = useQueryClient()
  const list = useAddresses()
  const [adding, setAdding] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ['account', 'addresses'] })
  const remove = useMutation({ mutationFn: accountApi.removeAddress, onSuccess: () => { void refresh(); notify.success('Endereço removido', { id: 'address-removed' }) }, onError: (e) => notifyApiError(e) })
  const makeDefault = useMutation({ mutationFn: accountApi.setDefaultAddress, onSuccess: () => { void refresh(); notify.success('Endereço padrão atualizado', { id: 'address-default' }) }, onError: (e) => notifyApiError(e) })
  const count = list.data?.length ?? 0
  return (
    <div>
      <h1 className="mb-4 text-2xl font-extrabold tracking-tight md:text-4xl">Endereços</h1>
      {list.isLoading ? <LoadingBlock /> : list.isError ? <ErrorState message={list.error.message} onRetry={() => void list.refetch()} /> : (
        <>
          <ul className="space-y-2">
            {list.data?.map((a) => (
              <li key={a.id} className="border border-border p-3 text-sm">
                <strong>{a.label}</strong>{a.is_default && ' · padrão'} · {a.recipient}<br />
                {a.street}, {a.number}{a.complement && ` ${a.complement}`} - {a.district}, {a.city}/{a.state} · {a.zip}
                <div className="mt-2 flex gap-4">
                  {!a.is_default && <button type="button" disabled={makeDefault.isPending} onClick={() => makeDefault.mutate(a.id)} className="font-bold underline">Tornar padrão</button>}
                  <button type="button" disabled={remove.isPending} onClick={() => { if (confirm('Excluir este endereço?')) remove.mutate(a.id) }} className="font-bold text-destructive underline">Excluir<span className="sr-only"> {a.label}</span></button>
                </div>
              </li>
            ))}
          </ul>
          {count === 0 && <p className="text-sm text-muted-foreground">Nenhum endereço salvo.</p>}
          {adding || count === 0 ? (
            <div className="mt-4"><AddressForm firstAddress={count === 0} onCancel={() => setAdding(false)} onSaved={() => setAdding(false)} /></div>
          ) : count < 3 ? (
            <button type="button" onClick={() => setAdding(true)} className="mt-4 text-sm font-bold underline">Adicionar endereço</button>
          ) : <p className="mt-4 text-sm text-muted-foreground">Limite de 3 endereços atingido.</p>}
        </>
      )}
    </div>
  )
}

export function PaymentsPage() {
  usePageTitle('Pagamentos')
  const qc = useQueryClient()
  const list = useCards()
  const title = useRef<HTMLHeadingElement>(null)
  const remove = useMutation({
    mutationFn: accountApi.removeCard,
    gcTime: 0,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['account', 'cards'] }); notify.success('Cartão removido', { id: 'card-removed' }); title.current?.focus() },
    onError: (e) => notifyApiError(e),
  })
  const count = list.data?.length ?? 0
  return (
    <div>
      <h1 ref={title} tabIndex={-1} className="mb-4 text-2xl font-extrabold tracking-tight outline-none md:text-4xl">Pagamentos</h1>
      {list.isLoading ? <LoadingBlock /> : list.isError ? <ErrorState message={list.error.message} onRetry={() => void list.refetch()} /> : (
        <>
          <ul className="space-y-2">
            {list.data?.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border border-border p-3 text-sm">
                <span><strong className="capitalize">{c.brand}</strong> •••• {c.last4}</span>
                <span className={isExpired(c) ? 'font-bold text-destructive' : 'text-muted-foreground'}>{isExpired(c) ? 'Vencido' : 'Validade'} {fmtExp(c)}</span>
                <button type="button" disabled={remove.isPending} onClick={() => { if (confirm('Excluir este cartão?')) remove.mutate(c.id) }} className="inline-flex h-11 items-center font-bold text-destructive underline">Excluir<span className="sr-only"> cartão final {c.last4}</span></button>
              </li>
            ))}
          </ul>
          {count === 0 && <p className="text-sm text-muted-foreground">Nenhum cartão salvo.</p>}
          <div className="mt-4">
            {count < MAX_CARDS ? <CardForm onSaved={() => title.current?.focus()} /> : <p className="text-sm text-muted-foreground">Limite de {MAX_CARDS} cartões atingido.</p>}
          </div>
        </>
      )}
    </div>
  )
}

const input = 'mt-1 h-11 w-full border border-input px-3 text-base md:text-sm'

export function SecurityPage() {
  usePageTitle('Segurança')
  const { signOut } = useCustomer()
  const navigate = useNavigate()
  const [pwdError, setPwdError] = useState<string>()
  const [delError, setDelError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const changePassword = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const code = String(f.get('code') ?? '').trim()
    setBusy(true)
    setPwdError(undefined)
    try {
      await accountApi.changePassword({ current_password: String(f.get('current')), new_password: String(f.get('next')), ...(code && { code }) })
      notify.success('Senha alterada. Entre de novo.', { id: 'password-changed' })
      await signOut(true)
      navigate('/entrar', { replace: true })
    } catch (err) {
      if (isTransient(err)) { setPwdError(undefined); notifyApiError(err) } else setPwdError(err instanceof Error ? err.message : 'Não foi possível alterar a senha.')
    } finally {
      setBusy(false)
    }
  }
  const exportData = async () => {
    try {
      const data = await accountApi.exportData()
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const a = document.createElement('a')
      a.href = url
      a.download = 'meus-dados.json'
      a.click()
      URL.revokeObjectURL(url)
      notify.success('Seus dados foram baixados.', { id: 'data-exported' })
    } catch (err) {
      notifyApiError(err, { fallback: 'Não foi possível exportar.', retry: () => void exportData() })
    }
  }
  const deleteAccount = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    if (String(f.get('confirm')) !== 'EXCLUIR') return setDelError('Digite EXCLUIR para confirmar.')
    setBusy(true)
    setDelError(undefined)
    try {
      await accountApi.deleteAccount({ password: String(f.get('password')), confirm: 'EXCLUIR' })
      await signOut(true)
      notify.success('Conta excluída.', { id: 'account-deleted' })
      navigate('/', { replace: true })
    } catch (err) {
      if (isTransient(err)) { setDelError(undefined); notifyApiError(err) } else setDelError(err instanceof Error ? err.message : 'Não foi possível excluir a conta.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="max-w-md space-y-10">
      <h1 className="text-2xl font-extrabold tracking-tight md:text-4xl">Segurança</h1>
      <form onSubmit={(e) => void changePassword(e)} aria-labelledby="h-pw" className="space-y-3">
        <h2 id="h-pw" className="text-lg font-extrabold">Trocar senha</h2>
        <div><label htmlFor="pw-cur" className="text-sm font-semibold">Senha atual</label><input id="pw-cur" name="current" type="password" autoComplete="current-password" required className={input} /></div>
        <div><label htmlFor="pw-new" className="text-sm font-semibold">Nova senha (12 a 128 caracteres)</label><input id="pw-new" name="next" type="password" autoComplete="new-password" required minLength={12} maxLength={128} className={input} /></div>
        <div><label htmlFor="pw-code" className="text-sm font-semibold">Código por e-mail (se pedido)</label><input id="pw-code" name="code" inputMode="numeric" maxLength={6} autoComplete="one-time-code" className={input} /></div>
        {pwdError && <InlineError>{pwdError}</InlineError>}
        <button disabled={busy} className="btn-brand h-11 px-6 text-sm disabled:opacity-50">Trocar senha</button>
      </form>
      <section aria-labelledby="h-ex" className="space-y-3">
        <h2 id="h-ex" className="text-lg font-extrabold">Exportar meus dados</h2>
        <p className="text-sm text-muted-foreground">Baixa um arquivo JSON com seu cadastro, endereços, cartões salvos (bandeira, final e validade), pedidos, pagamentos e carrinho.</p>
        <button type="button" onClick={() => void exportData()} className="h-11 border border-foreground px-6 text-sm font-bold">Baixar meus dados</button>
      </section>
      <form onSubmit={(e) => void deleteAccount(e)} aria-labelledby="h-del" className="space-y-3">
        <h2 id="h-del" className="text-lg font-extrabold text-destructive">Excluir conta</h2>
        <p className="text-sm text-muted-foreground">Remove seus dados pessoais; pedidos ficam anonimizados. Não dá para desfazer.</p>
        <div><label htmlFor="del-pw" className="text-sm font-semibold">Senha</label><input id="del-pw" name="password" type="password" autoComplete="current-password" required className={input} /></div>
        <div><label htmlFor="del-conf" className="text-sm font-semibold">Digite EXCLUIR para confirmar</label><input id="del-conf" name="confirm" autoComplete="off" required className={input} /></div>
        {delError && <InlineError>{delError}</InlineError>}
        <button disabled={busy} className="h-11 bg-destructive px-6 text-sm font-bold text-white disabled:opacity-50">Excluir minha conta</button>
      </form>
    </div>
  )
}
