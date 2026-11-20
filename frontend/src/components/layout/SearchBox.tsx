import { Search } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { useCategories } from '@/hooks/useShop'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { money, productHref, categoryHref } from '@/lib/product'
import { catalogApi } from '@/services/shop'

interface Option {
  key: string
  to: string
  label: string
  hint?: string
}

/** Busca com dropdown de categoria e sugestões (combobox ARIA, setas/Enter/Esc). */
export function SearchBox() {
  const navigate = useNavigate()
  const listId = useId()
  const wrap = useRef<HTMLFormElement>(null)
  const [text, setText] = useState('')
  const [category, setCategory] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const q = useDebouncedValue(text.trim(), 250)
  const categories = useCategories()
  const suggest = useQuery({
    queryKey: ['suggest', q],
    queryFn: ({ signal }) => catalogApi.suggest(q, signal),
    enabled: q.length >= 2,
    staleTime: 30_000,
  })

  const options: Option[] =
    q.length < 2 || !suggest.data
      ? []
      : [
          ...suggest.data.categories.map((c) => ({ key: `c-${c.category}`, to: categoryHref(c.category), label: c.label, hint: 'Categoria' })),
          ...suggest.data.products.map((p) => ({ key: p.product_id, to: productHref(p.product_id), label: p.title, hint: money(p.price_cents) })),
        ]
  const showList = open && options.length > 0

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const go = (to: string) => {
    setOpen(false)
    setActive(-1)
    navigate(to)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const picked = options[active]
    if (picked) return go(picked.to)
    const params = new URLSearchParams()
    if (text.trim()) params.set('q', text.trim())
    if (category) params.set('category', category)
    go(`/busca?${params}`)
  }

  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'ArrowDown' && options.length) {
      e.preventDefault()
      setOpen(true)
      setActive((a) => (a + 1) % options.length)
    } else if (e.key === 'ArrowUp' && options.length) {
      e.preventDefault()
      setActive((a) => (a <= 0 ? options.length - 1 : a - 1))
    }
  }

  return (
    <form ref={wrap} role="search" onSubmit={submit} className="relative flex w-full">
      <label htmlFor="search-cat" className="sr-only">
        Categoria
      </label>
      <select
        id="search-cat"
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        className="hidden h-11 max-w-40 shrink-0 border border-r-0 border-input bg-surface px-2 text-xs font-semibold md:block"
      >
        <option value="">Todas</option>
        {categories.data?.map((c) => (
          <option key={c.category} value={c.category}>
            {c.label}
          </option>
        ))}
      </select>
      <label htmlFor="search-q" className="sr-only">
        Buscar produtos
      </label>
      <input
        id="search-q"
        type="search"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        placeholder="Buscar produtos e categorias"
        value={text}
        maxLength={80}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
          setActive(-1)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
        className="h-11 min-w-0 flex-1 border border-input bg-background px-3 text-base outline-none focus:border-brand focus:ring-2 focus:ring-brand md:text-sm"
      />
      <button type="submit" className="btn-brand inline-flex h-11 w-12 items-center justify-center">
        <Search className="size-5" aria-hidden="true" />
        <span className="sr-only">Buscar</span>
      </button>
      <div aria-live="polite" className="sr-only">
        {showList ? `${options.length} sugestões` : ''}
      </div>
      {showList && (
        <ul id={listId} role="listbox" aria-label="Sugestões" className="absolute inset-x-0 top-full z-40 border border-border bg-popover shadow-md">
          {options.map((o, i) => (
            <li
              key={o.key}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => go(o.to)}
              className={`flex cursor-pointer items-center justify-between gap-3 px-3 py-2.5 text-sm ${i === active ? 'bg-accent' : 'hover:bg-accent'}`}
            >
              <span className="truncate">{o.label}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{o.hint}</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
