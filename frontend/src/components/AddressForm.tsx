import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useCustomer } from '@/app/customer-context'
import { notify } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { isZip, maskZip, normalizeZip, titleCase } from '@/lib/product'
import { ApiError } from '@/services/http'
import { accountApi, zipApi } from '@/services/shop'
import type { AddressInput } from '@/types/shop'

const UFS: Record<string, string> = {
  AC: 'Acre', AL: 'Alagoas', AP: 'Amapá', AM: 'Amazonas', BA: 'Bahia', CE: 'Ceará', DF: 'Distrito Federal', ES: 'Espírito Santo',
  GO: 'Goiás', MA: 'Maranhão', MT: 'Mato Grosso', MS: 'Mato Grosso do Sul', MG: 'Minas Gerais', PA: 'Pará', PB: 'Paraíba',
  PR: 'Paraná', PE: 'Pernambuco', PI: 'Piauí', RJ: 'Rio de Janeiro', RN: 'Rio Grande do Norte', RS: 'Rio Grande do Sul',
  RO: 'Rondônia', RR: 'Roraima', SC: 'Santa Catarina', SP: 'São Paulo', SE: 'Sergipe', TO: 'Tocantins',
}
const LABELS = ['Casa', 'Trabalho', 'Outro']
type Lookup = 'idle' | 'loading' | 'found' | 'manual'
type Errors = Partial<Record<'zip' | 'recipient' | 'street' | 'number' | 'district' | 'city' | 'state', string>>

const input = 'h-12 w-full border border-input bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground aria-[invalid=true]:border-2 aria-[invalid=true]:border-foreground read-only:bg-surface read-only:text-muted-foreground disabled:bg-surface disabled:text-muted-foreground md:h-11 md:text-sm'

function Field({ id, label, optional, error, hint, className, children }: { id: string; label: string; optional?: boolean; error?: string; hint?: string; className?: string; children: ReactNode }) {
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-sm font-semibold">
        {label}{optional && <span className="font-normal text-muted-foreground"> (opcional)</span>}
      </label>
      {children}
      {hint && !error && <p id={`${id}-hint`} className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      {error && <p id={`${id}-err`} className="mt-1 text-sm font-medium text-destructive">{error}</p>}
    </div>
  )
}

export function AddressForm({ onSaved, onCancel, firstAddress }: { onSaved: (id: string) => void; onCancel?: () => void; firstAddress?: boolean }) {
  const qc = useQueryClient()
  const { customer } = useCustomer()
  const save = useMutation({
    mutationFn: (body: AddressInput) => accountApi.addAddress(body),
    onSuccess: (a) => { void qc.invalidateQueries({ queryKey: ['account', 'addresses'] }); notify.success('Endereço salvo', { id: 'address-saved' }); onSaved(a.id) },
  })
  const [zip, setZip] = useState('')
  const [street, setStreet] = useState('')
  const [district, setDistrict] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [lookup, setLookup] = useState<Lookup>('idle')
  const [unlock, setUnlock] = useState(false)
  const [noNumber, setNoNumber] = useState(false)
  const [label, setLabel] = useState('Casa')
  const [errors, setErrors] = useState<Errors>({})
  const numberRef = useRef<HTMLInputElement>(null)
  const streetRef = useRef<HTMLInputElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const abort = useRef<AbortController>(undefined)
  useEffect(() => () => abort.current?.abort(), [])

  const onZip = (raw: string) => {
    const masked = maskZip(raw)
    setZip(masked)
    setErrors((e) => ({ ...e, zip: undefined }))
    abort.current?.abort()
    if (!isZip(masked)) { setLookup('idle'); return }
    const ctl = new AbortController()
    abort.current = ctl
    setLookup('loading')
    zipApi.lookup(normalizeZip(masked), ctl.signal).then((r) => {
      setCity(titleCase(r.city)); setState(r.state.toUpperCase()); setLookup('found'); setUnlock(false)
      if (r.street) setStreet(r.street)
      if (r.district) setDistrict(r.district)
      setErrors((e) => ({ ...e, city: undefined, state: undefined, ...(r.street && { street: undefined }), ...(r.district && { district: undefined }) }))
      ;(r.street ? numberRef : streetRef).current?.focus()
    }).catch((e: unknown) => {
      if (ctl.signal.aborted) return
      setLookup('manual')
      if (e instanceof ApiError && e.status === 404) notify.info('CEP não encontrado.', { id: 'zip-not-found' })
    })
  }

  const locked = lookup === 'found' && !unlock
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const v = (k: string) => String(f.get(k) ?? '').trim()
    const err: Errors = {}
    if (!isZip(zip)) err.zip = 'Informe o CEP com 8 dígitos.'
    if (!v('recipient')) err.recipient = 'Informe quem vai receber.'
    if (!street.trim()) err.street = 'Informe a rua.'
    if (!noNumber && !v('number')) err.number = 'Informe o número ou marque "Sem número".'
    if (!district.trim()) err.district = 'Informe o bairro.'
    if (!city.trim()) err.city = 'Informe a cidade.'
    if (!state) err.state = 'Escolha o estado.'
    setErrors(err)
    const first = Object.keys(err)[0]
    if (first) { formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus(); return }
    save.mutate({
      label, recipient: v('recipient'), zip: normalizeZip(zip), street: street.trim(), number: noNumber ? 'S/N' : v('number'),
      complement: v('complement') || null, district: district.trim(), city: city.trim(), state, is_default: f.get('is_default') === 'on',
    })
  }
  const a11y = (name: keyof Errors, hint?: boolean) => ({
    id: `a-${name}`, name, 'aria-invalid': !!errors[name], 'aria-describedby': errors[name] ? `a-${name}-err` : hint ? `a-${name}-hint` : undefined,
  })
  const count = Object.keys(errors).length

  return (
    <form ref={formRef} onSubmit={submit} noValidate aria-busy={save.isPending} className="space-y-5 border border-border p-4 md:p-6">
      <p className="text-xs text-muted-foreground">Todos os campos são obrigatórios, exceto os marcados como opcionais.</p>
      {count > 0 && <p role="alert" className="border border-foreground px-3 py-2 text-sm font-semibold">Corrija {count} {count === 1 ? 'campo' : 'campos'} para continuar.</p>}

      <div className="grid gap-x-4 gap-y-5 md:grid-cols-6">
        <Field id="a-zip" label="CEP" error={errors.zip} className="md:col-span-2">
          <input {...a11y('zip')} value={zip} onChange={(e) => onZip(e.target.value)} inputMode="numeric" autoComplete="postal-code" enterKeyHint="next" maxLength={9} placeholder="00000-000" className={input} />
        </Field>
        <div className="flex flex-col justify-end text-sm md:col-span-4 md:pb-3" aria-live="polite">
          {lookup === 'loading' && <span className="text-muted-foreground">Buscando endereço…</span>}
          {lookup === 'manual' && <span className="text-muted-foreground">Não encontramos esse CEP. Preencha cidade e estado manualmente.</span>}
          <a href="https://buscacepinter.correios.com.br/app/endereco/index.php" target="_blank" rel="noopener noreferrer" className="w-fit py-2 font-semibold underline md:py-0">Não sei meu CEP<span className="sr-only"> (abre site dos Correios)</span></a>
        </div>

        <Field id="a-street" label="Rua" error={errors.street} className="md:col-span-4">
          <input {...a11y('street')} ref={streetRef} value={street} onChange={(e) => setStreet(e.target.value)} autoComplete="address-line1" enterKeyHint="next" maxLength={120} className={input} />
        </Field>
        <Field id="a-number" label="Número" error={errors.number} className="md:col-span-2">
          <input {...a11y('number')} ref={numberRef} disabled={noNumber} placeholder={noNumber ? 'S/N' : undefined} inputMode="numeric" autoComplete="off" enterKeyHint="next" maxLength={10} className={input} />
          <label className="mt-1 flex min-h-11 items-center gap-2 text-sm md:min-h-8">
            <input type="checkbox" checked={noNumber} onChange={(e) => { setNoNumber(e.target.checked); setErrors((x) => ({ ...x, number: undefined })) }} className="size-5 accent-foreground md:size-4" />
            Sem número
          </label>
        </Field>

        <Field id="a-complement" label="Complemento" optional hint="Apto, bloco, casa 2" className="md:col-span-3">
          <input id="a-complement" name="complement" aria-describedby="a-complement-hint" autoComplete="address-line2" enterKeyHint="next" maxLength={120} className={input} />
        </Field>
        <Field id="a-district" label="Bairro" error={errors.district} className="md:col-span-3">
          <input {...a11y('district')} value={district} onChange={(e) => setDistrict(e.target.value)} autoComplete="address-level3" enterKeyHint="next" maxLength={120} className={input} />
        </Field>

        <Field id="a-city" label="Cidade" error={errors.city} className="md:col-span-4">
          <input {...a11y('city')} value={city} onChange={(e) => setCity(e.target.value)} readOnly={locked} autoComplete="address-level2" enterKeyHint="next" maxLength={120} className={input} />
        </Field>
        <Field id="a-state" label="Estado (UF)" error={errors.state} className="md:col-span-2">
          <select {...a11y('state')} value={state} onChange={(e) => setState(e.target.value)} disabled={locked} autoComplete="address-level1" className={cn(input, 'appearance-auto')}>
            <option value="">Selecione</option>
            {Object.entries(UFS).map(([uf, name]) => <option key={uf} value={uf}>{uf} · {name}</option>)}
          </select>
        </Field>
        {locked && (
          <p className="text-sm text-muted-foreground md:col-span-6">
            Preenchido pelo CEP. <button type="button" onClick={() => setUnlock(true)} className="inline-flex min-h-11 items-center font-semibold text-foreground underline md:min-h-0">Alterar cidade e estado</button>
          </p>
        )}
      </div>

      <div className="grid gap-x-4 gap-y-5 border-t border-border pt-5 md:grid-cols-2">
        <Field id="a-recipient" label="Quem vai receber" error={errors.recipient}>
          <input {...a11y('recipient')} defaultValue={customer?.nickname?.split(' ')[0] ?? ''} autoComplete="name" enterKeyHint="done" maxLength={120} className={input} />
        </Field>
        <fieldset>
          <legend className="mb-1 text-sm font-semibold">Salvar como</legend>
          <div className="flex gap-2">
            {LABELS.map((l) => (
              <label key={l} className={cn('flex h-12 flex-1 cursor-pointer items-center justify-center border text-sm font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-foreground md:h-11', label === l ? 'border-foreground bg-foreground text-background' : 'border-input')}>
                <input type="radio" name="label" value={l} checked={label === l} onChange={() => setLabel(l)} className="sr-only" />
                {l}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <label className="flex min-h-11 items-center gap-2 text-sm">
        <input type="checkbox" name="is_default" className="size-5 accent-foreground md:size-4" />
        Definir como endereço padrão
      </label>

      {save.error && <p role="alert" className="text-sm font-medium text-destructive">{save.error.message}</p>}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center">
        {onCancel && !firstAddress && <button type="button" onClick={onCancel} className="h-12 px-6 text-sm font-bold underline sm:h-11">Cancelar</button>}
        <button disabled={save.isPending} className="btn-brand h-12 flex-1 px-8 text-sm disabled:opacity-50 sm:flex-none">{save.isPending ? 'Salvando…' : 'Salvar e continuar'}</button>
      </div>
    </form>
  )
}
