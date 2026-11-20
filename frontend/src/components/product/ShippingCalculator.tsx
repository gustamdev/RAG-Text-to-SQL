import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { InlineError } from '@/components/StateViews'
import { setZip, useZip } from '@/hooks/useZip'
import { isZip, maskZip, money, normalizeZip } from '@/lib/product'
import type { FreightResult } from '@/types/shop'

/** Cálculo de frete por CEP; `fetcher` decide se é de um produto ou do carrinho. */
export function ShippingCalculator({ fetcher, id }: { fetcher: (zip: string) => Promise<FreightResult>; id: string }) {
  const saved = useZip()
  const [value, setValue] = useState(maskZip(saved))
  const [invalid, setInvalid] = useState(false)
  const calc = useMutation({ mutationFn: fetcher, onSuccess: (r) => setZip(r.zip) })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!isZip(value)) return setInvalid(true)
    setInvalid(false)
    calc.mutate(normalizeZip(value))
  }
  const err = invalid ? 'CEP inválido. Use 8 dígitos.' : calc.error?.message

  return (
    <form onSubmit={submit} noValidate aria-busy={calc.isPending}>
      <label htmlFor={`${id}-zip`} className="text-sm font-semibold">Calcular frete</label>
      <div className="mt-1 flex gap-2">
        <input
          id={`${id}-zip`}
          inputMode="numeric"
          autoComplete="postal-code"
          placeholder="00000-000"
          value={value}
          onChange={(e) => setValue(maskZip(e.target.value))}
          aria-invalid={!!err}
          aria-describedby={err ? `${id}-zip-err` : undefined}
          className="h-11 min-w-0 flex-1 border border-input px-3 text-base md:text-sm"
        />
        <button disabled={calc.isPending} className="h-11 border border-foreground px-5 text-sm font-bold disabled:opacity-50">
          {calc.isPending ? 'Calculando…' : 'OK'}
        </button>
      </div>
      {err && <InlineError id={`${id}-zip-err`}>{err}</InlineError>}
      {calc.data && (
        <ul className="mt-2 space-y-1 text-sm" aria-live="polite">
          {calc.data.options.map((o) => (
            <li key={o.code}>
              <span className="font-semibold">{o.label}</span>: {o.days_min} a {o.days_max} dias úteis, <span className="tabular-nums">{money(o.price_cents)}</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
