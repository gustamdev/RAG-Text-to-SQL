import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { EMPTY_CARD, cardIssue, maskExp, maskPan, toCardInput, type CardField, type CardIssue, type CardValue } from '@/lib/cards'
import { notify } from '@/lib/notify'
import { accountApi } from '@/services/shop'
import type { SavedCard } from '@/types/shop'
import { InlineError } from '@/components/StateViews'

const field = 'mt-1 h-11 w-full border border-input px-3 text-base md:text-sm'

/** Campos do cartão (controlados), compartilhados entre checkout e "Adicionar cartão". Ids: `${id}-num|nm|exp|cvv`; o erro (`${id}-err`) marca o campo com aria-invalid. */
export function CardFields({ value, onChange, id = 'c', issue }: { value: CardValue; onChange: (v: CardValue) => void; id?: string; issue?: CardIssue }) {
  const err = (f: CardField) => (issue?.field === f ? { 'aria-invalid': true as const, 'aria-describedby': `${id}-err` } : {})
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2"><label htmlFor={`${id}-num`} className="text-sm font-semibold">Número do cartão</label>
        <input id={`${id}-num`} {...err('num')} inputMode="numeric" autoComplete="cc-number" maxLength={19} value={value.number} onChange={(e) => onChange({ ...value, number: maskPan(e.target.value) })} className={field} /></div>
      <div className="sm:col-span-2"><label htmlFor={`${id}-nm`} className="text-sm font-semibold">Nome impresso</label>
        <input id={`${id}-nm`} {...err('nm')} autoComplete="cc-name" maxLength={60} value={value.holder} onChange={(e) => onChange({ ...value, holder: e.target.value.toUpperCase() })} className={field} /></div>
      <div><label htmlFor={`${id}-exp`} className="text-sm font-semibold">Validade (MM/AA)</label>
        <input id={`${id}-exp`} {...err('exp')} inputMode="numeric" autoComplete="cc-exp" maxLength={5} value={value.exp} onChange={(e) => onChange({ ...value, exp: maskExp(e.target.value) })} className={field} /></div>
      <div><label htmlFor={`${id}-cvv`} className="text-sm font-semibold">CVV</label>
        <input id={`${id}-cvv`} {...err('cvv')} inputMode="numeric" autoComplete="cc-csc" maxLength={4} value={value.cvv} onChange={(e) => onChange({ ...value, cvv: e.target.value.replace(/\D/g, '').slice(0, 4) })} className={field} /></div>
    </div>
  )
}

/** Adiciona um cartão à conta. O CVV só é enviado e descartado. */
export function CardForm({ onSaved }: { onSaved?: () => void }) {
  const qc = useQueryClient()
  const [card, setCard] = useState<CardValue>(EMPTY_CARD)
  const [issue, setIssue] = useState<CardIssue>()
  const save = useMutation({
    mutationFn: () => accountApi.addCard(toCardInput(card)),
    gcTime: 0,
    onSuccess: (saved) => {
      // 200 = cartão já existia (validade atualizada); 201 = novo. O corpo não distingue, então compara com a lista em cache.
      const existed = qc.getQueryData<SavedCard[]>(['account', 'cards'])?.some((c) => c.id === saved.id)
      void qc.invalidateQueries({ queryKey: ['account', 'cards'] })
      notify.success(existed ? 'Cartão atualizado' : 'Cartão salvo', { id: 'card-saved' })
      setCard(EMPTY_CARD)
      onSaved?.()
    },
    onError: (e) => setIssue({ message: e.message }),
    // Número e CVV não ficam em memória depois do envio, com sucesso ou erro.
    onSettled: () => setCard((c) => ({ ...c, number: '', cvv: '' })),
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const err = cardIssue(card)
    setIssue(err)
    if (!err) save.mutate()
  }
  return (
    <form onSubmit={submit} noValidate aria-labelledby="h-addcard" aria-busy={save.isPending} className="max-w-md space-y-4 border border-border p-4 md:p-6">
      <h2 id="h-addcard" className="text-lg font-extrabold">Adicionar cartão</h2>
      <CardFields id="nc" value={card} onChange={setCard} issue={issue} />
      {issue && <InlineError id="nc-err">{issue.message}</InlineError>}
      <button disabled={save.isPending} className="btn-brand h-11 px-6 text-sm disabled:opacity-50">{save.isPending ? 'Salvando…' : 'Salvar cartão'}</button>
    </form>
  )
}
