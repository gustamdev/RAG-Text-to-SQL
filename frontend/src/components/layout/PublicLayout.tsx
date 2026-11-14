import { NavLink, Outlet, ScrollRestoration } from 'react-router'
import { cn } from '@/lib/utils'
import { Brand } from './Brand'

const navLink = ({ isActive }: { isActive: boolean }) =>
  cn(
    'px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors hover:text-foreground',
    isActive ? 'text-foreground' : 'text-muted-foreground',
  )

export function PublicLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-4 px-4 md:px-8">
          <Brand />
          <nav aria-label="Principal" className="flex items-center">
            <NavLink to="/produtos" className={navLink}>
              Catálogo
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-3 px-4 py-8 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between md:px-8">
          <Brand className="text-foreground" />
          <p className="max-w-xl md:text-right">
            Dados do conjunto público{' '}
            <a
              className="underline underline-offset-2 hover:text-foreground"
              href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
              target="_blank"
              rel="noreferrer noopener"
            >
              Brazilian E-Commerce Public Dataset by Olist
            </a>{' '}
            (Kaggle), licença{' '}
            <a
              className="underline underline-offset-2 hover:text-foreground"
              href="https://creativecommons.org/licenses/by-nc-sa/4.0/"
              target="_blank"
              rel="noreferrer noopener"
            >
              CC BY-NC-SA 4.0
            </a>
            . Uso não comercial. Os produtos não têm nome nem foto no dataset: os rótulos são sintéticos.
          </p>
        </div>
      </footer>
      <ScrollRestoration />
    </div>
  )
}
