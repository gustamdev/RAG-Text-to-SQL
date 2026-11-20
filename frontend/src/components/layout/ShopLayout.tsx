import { Home, MapPin, Search, ShoppingCart, User, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, ScrollRestoration, useLocation } from 'react-router'
import { useCustomer } from '@/app/customer-context'
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { useCart, useCategories } from '@/hooks/useShop'
import { setZip, useZip } from '@/hooks/useZip'
import { categoryHref, isZip, maskZip, normalizeZip } from '@/lib/product'
import { cn } from '@/lib/utils'
import { Brand } from './Brand'
import { SearchBox } from './SearchBox'

function ZipPicker() {
  const zip = useZip()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [error, setError] = useState(false)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!isZip(value)) return setError(true)
    setZip(normalizeZip(value))
    setOpen(false)
  }
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); setValue(maskZip(zip)); setError(false) }}>
      <DialogTrigger className="hidden items-center gap-1.5 text-left text-xs leading-tight hover:underline focus-visible:outline-2 focus-visible:outline-ring lg:flex">
        <MapPin className="size-4" aria-hidden="true" />
        <span>
          <span className="block text-muted-foreground">Enviar para</span>
          <span className="font-bold tabular-nums">{zip ? maskZip(zip) : 'Informe o CEP'}</span>
        </span>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Enviar para o CEP</DialogTitle>
        <DialogDescription>Usamos o CEP para sugerir o frete. Ele fica só neste navegador.</DialogDescription>
        <form onSubmit={submit} noValidate className="flex flex-col gap-2">
          <label htmlFor="zip-hdr" className="text-sm font-semibold">CEP</label>
          <input
            id="zip-hdr"
            inputMode="numeric"
            autoComplete="postal-code"
            value={value}
            onChange={(e) => setValue(maskZip(e.target.value))}
            aria-invalid={error}
            aria-describedby={error ? 'zip-hdr-err' : undefined}
            className="h-11 border border-input px-3 text-base"
          />
          {error && <p id="zip-hdr-err" role="alert" className="text-sm font-medium text-destructive">CEP inválido.</p>}
          <button className="btn-brand h-11 px-6 text-sm">Usar este CEP</button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function CartLink({ className }: { className?: string }) {
  const { cart } = useCart()
  return (
    <Link to="/carrinho" className={cn('relative inline-flex items-center gap-1.5 focus-visible:outline-2 focus-visible:outline-ring', className)}>
      <ShoppingCart className="size-6" aria-hidden="true" />
      <span className="hidden text-sm font-bold md:inline">Carrinho</span>
      <span aria-hidden="true" className="absolute -right-2 -top-2 min-w-5 bg-brand px-1 text-center text-[11px] font-bold leading-5 text-brand-foreground md:static md:ml-0.5">
        {cart.item_count}
      </span>
      <span className="sr-only">, {cart.item_count} itens</span>
    </Link>
  )
}

function Account() {
  const { customer, signOut } = useCustomer()
  return customer ? (
    <div className="hidden items-center gap-3 text-sm md:flex">
      <Link to="/conta" className="font-bold hover:underline">Olá, {customer.nickname ?? 'cliente'}</Link>
      <Link to="/conta/pedidos" className="hover:underline">Pedidos</Link>
      <button type="button" onClick={() => void signOut()} className="text-muted-foreground hover:underline">Sair</button>
    </div>
  ) : (
    <div className="hidden items-center gap-2 text-sm md:flex">
      <Link to="/entrar" className="border border-foreground px-4 py-2 font-bold hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">Entrar</Link>
      <Link to="/cadastro" className="btn-brand px-4 py-2 focus-visible:outline-2">Cadastrar</Link>
    </div>
  )
}

function TabBar() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    cn('flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold', isActive ? 'text-foreground' : 'text-muted-foreground')
  return (
    <nav aria-label="Navegação inferior" className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-background pb-[env(safe-area-inset-bottom)] md:hidden">
      <NavLink to="/" end className={tab}><Home className="size-5" aria-hidden="true" />Início</NavLink>
      <NavLink to="/busca" className={tab}><Search className="size-5" aria-hidden="true" />Busca</NavLink>
      <NavLink to="/carrinho" className={tab}><ShoppingCart className="size-5" aria-hidden="true" />Carrinho</NavLink>
      <NavLink to="/conta" className={tab}><User className="size-5" aria-hidden="true" />Conta</NavLink>
    </nav>
  )
}

export function ShopLayout() {
  const { pathname } = useLocation()
  const categories = useCategories()
  const [notice, setNotice] = useState(() => sessionStorage.getItem('olist.shop.notice') !== '1')
  const checkout = pathname.startsWith('/checkout')

  return (
    <div className="flex min-h-dvh flex-col pb-14 md:pb-0">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:bg-background focus:p-3 focus:font-bold">
        Pular para o conteúdo
      </a>
      {notice && (
        <div className="flex items-center justify-center gap-3 bg-foreground px-4 py-1.5 text-xs text-background">
          <p>Loja de demonstração. Pagamento simulado: nenhum valor é cobrado.</p>
          <button
            type="button"
            onClick={() => { sessionStorage.setItem('olist.shop.notice', '1'); setNotice(false) }}
            className="shrink-0 focus-visible:outline-2 focus-visible:outline-background"
          >
            <X className="size-4" aria-hidden="true" />
            <span className="sr-only">Fechar aviso</span>
          </button>
        </div>
      )}
      <header className="sticky top-0 z-30 border-b border-border bg-background">
        {checkout ? (
          <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between px-4 md:px-8">
            <Brand />
            <p className="text-xs font-semibold text-muted-foreground">Compra segura (simulada)</p>
          </div>
        ) : (
          <>
            <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 md:flex-nowrap md:gap-6 md:px-8 md:py-3">
              <Brand className="order-1" />
              <div className="order-3 w-full md:order-2 md:flex-1"><SearchBox /></div>
              <div className="order-2 ml-auto flex items-center gap-5 md:order-3 md:ml-0">
                <ZipPicker />
                <Account />
                <CartLink />
              </div>
            </div>
            <nav aria-label="Categorias" className="border-t border-border">
              <ul className="no-scrollbar mx-auto flex max-w-[1600px] gap-1 overflow-x-auto px-4 md:px-8">
                <li><Link to="/busca" className="block whitespace-nowrap px-3 py-2.5 text-xs font-bold uppercase tracking-wider">Todos</Link></li>
                {categories.data?.slice(0, 8).map((c) => (
                  <li key={c.category}>
                    <Link to={categoryHref(c.category)} className="block whitespace-nowrap px-3 py-2.5 text-xs font-semibold text-muted-foreground hover:text-foreground">
                      {c.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </>
        )}
      </header>

      <main id="conteudo" className="flex-1 focus:outline-none" tabIndex={-1}>
        <Outlet />
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-8 text-xs text-muted-foreground md:px-8">
          <nav aria-label="Rodapé" className="flex flex-wrap gap-x-6 gap-y-2 font-semibold text-foreground">
            <Link to="/sobre">Sobre esta demo</Link>
            <Link to="/privacidade">Privacidade</Link>
            <Link to="/termos">Termos</Link>
            <Link to="/conta">Minha conta</Link>
          </nav>
          <p className="max-w-3xl">
            Loja de demonstração com pagamento simulado. Dados do{' '}
            <a className="underline underline-offset-2 hover:text-foreground" href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce" target="_blank" rel="noreferrer noopener">
              Brazilian E-Commerce Public Dataset by Olist
            </a>{' '}
            (Kaggle), licença{' '}
            <a className="underline underline-offset-2 hover:text-foreground" href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noreferrer noopener">
              CC BY-NC-SA 4.0
            </a>
            . Uso não comercial. Produtos simulados: sem foto, aparece a marca da loja.
          </p>
        </div>
      </footer>
      {!checkout && <TabBar />}
      <ScrollRestoration />
    </div>
  )
}
