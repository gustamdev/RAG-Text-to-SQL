import { Boxes, LayoutDashboard, MessageSquareText, Tags, type LucideIcon } from 'lucide-react'
import { Link, NavLink } from 'react-router'
import { Brand, BrandMark } from '@/components/layout/Brand'
import { cn } from '@/lib/utils'

interface Item {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

const ITEMS: Item[] = [
  { to: '/', label: 'Visão geral', icon: LayoutDashboard, end: true },
  { to: '/produtos', label: 'Produtos', icon: Boxes },
  { to: '/categorias', label: 'Categorias', icon: Tags },
  { to: '/assistente', label: 'Assistente', icon: MessageSquareText },
]

/**
 * Navegação do backoffice. Usada fixa no desktop e dentro do Sheet no mobile (`onNavigate` fecha o Sheet).
 * `collapsed`: só ícones (desktop), para liberar espaço, como no assistente.
 */
export function Sidebar({ onNavigate, collapsed = false }: { onNavigate?: () => void; collapsed?: boolean }) {
  return (
    <div className="flex h-full flex-col">
      <div className={cn('flex h-16 shrink-0 items-center border-b border-border', collapsed ? 'justify-center' : 'px-5')}>
        {collapsed ? (
          <Link to="/" aria-label="Olist Insights">
            <BrandMark />
          </Link>
        ) : (
          <Brand to="/" onClick={onNavigate} />
        )}
      </div>
      <nav aria-label="Backoffice" className="flex-1 space-y-0.5 p-3">
        {ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end ?? false}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 text-sm font-semibold transition-colors',
                collapsed && 'justify-center',
                isActive ? 'bg-foreground text-background' : 'text-muted-foreground hover:bg-accent hover:text-foreground',
              )
            }
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            {!collapsed && label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
