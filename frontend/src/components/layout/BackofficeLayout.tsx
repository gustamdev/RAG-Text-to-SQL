import { LogOut, Menu, Store } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { Sidebar } from '@/components/backoffice/Sidebar'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { useAuth } from '@/hooks/useAuth'

/**
 * Casca do backoffice: sidebar fixa no desktop, Sheet no mobile, topbar com a conta e a área de
 * conteúdo rolável. A altura é definida (h-dvh) para o chat preencher o espaço sem rolagem dupla.
 */
export function BackofficeLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const mainRef = useRef<HTMLElement>(null)

  // A rolagem é do <main>, não da janela: volta ao topo a cada troca de rota.
  useEffect(() => {
    mainRef.current?.scrollTo(0, 0)
  }, [pathname])

  function signOut() {
    logout()
    navigate('/backoffice/login', { replace: true })
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <aside className="hidden w-60 shrink-0 border-r border-border lg:block">
        <Sidebar />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border px-4 md:px-6">
          <div className="flex items-center gap-2">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Abrir menu">
                  <Menu />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-64 p-0 sm:max-w-64">
                <SheetTitle className="sr-only">Menu do backoffice</SheetTitle>
                <SheetDescription className="sr-only">Navegação entre as telas do backoffice.</SheetDescription>
                <Sidebar onNavigate={() => setOpen(false)} />
              </SheetContent>
            </Sheet>
            <span className="eyebrow text-muted-foreground">Backoffice</span>
          </div>

          <div className="flex min-w-0 items-center gap-1 sm:gap-3">
            <Link
              to="/produtos"
              className="inline-flex items-center gap-1.5 px-2 py-2 text-xs font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground"
            >
              <Store className="size-4" aria-hidden="true" />
              <span className="hidden sm:inline">Ver vitrine</span>
              <span className="sr-only sm:hidden">Ver vitrine</span>
            </Link>
            <span className="hidden max-w-[16rem] truncate text-xs text-muted-foreground md:inline" title={user?.email}>
              {user?.email}
            </span>
            <Button variant="outline" size="sm" onClick={signOut}>
              <LogOut aria-hidden="true" />
              Sair
            </Button>
          </div>
        </header>

        <main ref={mainRef} className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
