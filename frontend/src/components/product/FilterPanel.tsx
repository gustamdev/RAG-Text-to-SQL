import { useState } from 'react'
import type { CategoryOut } from '@/types/shop'

export interface FilterState {
  category: string
  minPrice: string
  maxPrice: string
  minRating: string
  inStock: boolean
}

/** Filtros laterais; cada mudança vai para a URL (pai). Preço aplica no envio. */
export function FilterPanel({
  value,
  categories,
  onChange,
  onCategory,
}: {
  value: FilterState
  categories: CategoryOut[] | undefined
  onChange: (changes: Record<string, string | undefined>) => void
  onCategory: (category: string) => void
}) {
  const [min, setMin] = useState(value.minPrice)
  const [max, setMax] = useState(value.maxPrice)
  const input = 'h-11 w-full border border-input px-2 text-base md:h-9 md:text-sm'
  const legend = 'mb-2 text-xs font-extrabold uppercase tracking-wider'

  return (
    <div className="space-y-6">
      <fieldset>
        <legend className={legend}>Categoria</legend>
        <label htmlFor="f-cat" className="sr-only">Categoria</label>
        <select id="f-cat" value={value.category} onChange={(e) => onCategory(e.target.value)} className={input}>
          <option value="">Todas</option>
          {categories?.map((c) => (
            <option key={c.category} value={c.category}>{c.label}</option>
          ))}
        </select>
      </fieldset>

      <fieldset>
        <legend className={legend}>Preço (R$)</legend>
        <form
          noValidate
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            onChange({ min_price: min.replace(/\D/g, ''), max_price: max.replace(/\D/g, '') })
          }}
        >
          <label className="flex-1"><span className="sr-only">Preço mínimo em reais</span>
            <input inputMode="numeric" placeholder="Mín" value={min} onChange={(e) => setMin(e.target.value)} className={input} />
          </label>
          <span aria-hidden="true">-</span>
          <label className="flex-1"><span className="sr-only">Preço máximo em reais</span>
            <input inputMode="numeric" placeholder="Máx" value={max} onChange={(e) => setMax(e.target.value)} className={input} />
          </label>
          <button className="h-11 border border-input px-3 text-xs font-bold md:h-9">OK</button>
        </form>
      </fieldset>

      <fieldset>
        <legend className={legend}>Nota</legend>
        {['', '4', '3', '2'].map((r) => (
          <label key={r} className="flex min-h-11 items-center gap-2 text-sm md:min-h-8">
            <input type="radio" name="min_rating" checked={value.minRating === r} onChange={() => onChange({ min_rating: r || undefined })} />
            {r ? `${r} estrelas ou mais` : 'Qualquer'}
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend className={legend}>Disponibilidade</legend>
        <label className="flex min-h-11 items-center gap-2 text-sm md:min-h-8">
          <input type="checkbox" checked={value.inStock} onChange={(e) => onChange({ in_stock: e.target.checked ? 'true' : undefined })} />
          Somente em estoque
        </label>
      </fieldset>
    </div>
  )
}
