import { Boxes, LayoutDashboard, MessageSquareText, Tags, type LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router'
import { Brand } from '@/components/layout/Brand'
import { cn } from '@/lib/utils'

interface Item {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

const ITEMS: Item[] = [
  { to: '/backoffice', label: 'Visão geral', icon: LayoutDashboard, end: true },
  { to: '/backoffice/produtos', label: 'Produtos', icon: Boxes },
  { to: '/backoffice/categorias', label: 'Categorias', icon: Tags },
  { to: '/backoffice/assistente', label: 'Assistente', icon: MessageSquareText },
]

/** Navegação do backoffice. Usada fixa no desktop e dentro do Sheet no mobile (`onNavigate` fecha o Sheet). */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center border-b border-border px-5">
        <Brand to="/backoffice" onClick={onNavigate} />
      </div>
      <nav aria-label="Backoffice" className="flex-1 space-y-0.5 p-3">
        {ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end ?? false}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 text-sm font-semibold transition-colors',
                isActive ? 'bg-foreground text-background' : 'text-muted-foreground hover:bg-accent hover:text-foreground',
              )
            }
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
