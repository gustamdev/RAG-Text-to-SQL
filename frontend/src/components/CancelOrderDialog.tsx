import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { InlineError } from '@/components/StateViews'
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Select } from '@/components/ui/select'
import { notify, notifyApiError } from '@/lib/notify'
import { loadOpenOrder, clearOpenOrder } from '@/lib/openOrder'
import { CANCEL_REASON_LABEL, money } from '@/lib/product'
import { ApiError } from '@/services/http'
import { accountApi } from '@/services/shop'
import type { CancelReason, OrderSummary } from '@/types/shop'

type Target = Pick<OrderSummary, 'order_id' | 'state' | 'total_cents'>

const btn = 'inline-flex h-12 items-center justify-center border border-foreground px-6 text-sm font-bold focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50 sm:h-11'

/** Confirmação única de cancelamento (lista e detalhe). `order` null = fechado. */
export function CancelOrderDialog({ order, onClose }: { order: Target | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [reason, setReason] = useState<CancelReason | ''>('')
  const [error, setError] = useState<string | null>(null)
  const paid = order?.state === 'paid'
  const id = order?.order_id ?? ''

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['account', 'orders'] })
    void qc.invalidateQueries({ queryKey: ['account', 'order', id] })
  }
  const cancel = useMutation({
    mutationFn: () => accountApi.cancel(id, reason || undefined),
    onSuccess: (o) => {
      if (loadOpenOrder()?.id === id) clearOpenOrder()
      refresh()
      notify.success(o.refund_cents ? `Pedido cancelado. Reembolso de ${money(o.refund_cents)} (simulado).` : 'Pedido cancelado', { id: 'order-cancelled' })
      onClose()
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) { notify.error(e.message); refresh(); onClose() }
      else if (e instanceof ApiError) setError(e.message)
      else notifyApiError(e)
    },
  })

  const close = () => { if (!cancel.isPending) { setError(null); setReason(''); onClose() } }

  return (
    <AlertDialog open={order !== null} onOpenChange={(o) => { if (!o) close() }}>
      <AlertDialogContent className="max-w-md rounded-none sm:rounded-none">
        <AlertDialogHeader>
          <AlertDialogTitle className="font-extrabold">Cancelar pedido #{id.slice(0, 6).toUpperCase()}?</AlertDialogTitle>
          <AlertDialogDescription className="text-foreground">
            {paid && order ? `Vamos reembolsar ${money(order.total_cents)} (simulado) e devolver os itens ao estoque.` : 'O pedido será cancelado e os itens voltam ao estoque.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div>
          <label htmlFor="cancel-reason" className="text-sm font-semibold">Motivo (opcional)</label>
          <Select id="cancel-reason" value={reason} disabled={cancel.isPending} onChange={(e) => setReason(e.target.value as CancelReason | '')} className="mt-1 h-11 rounded-none border-foreground">
            <option value="">Prefiro não informar</option>
            {(Object.keys(CANCEL_REASON_LABEL) as CancelReason[]).map((k) => <option key={k} value={k}>{CANCEL_REASON_LABEL[k]}</option>)}
          </Select>
        </div>
        {error && <InlineError>{error}</InlineError>}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" onClick={close} disabled={cancel.isPending} className={btn}>Manter pedido</button>
          <button type="button" onClick={() => { setError(null); cancel.mutate() }} disabled={cancel.isPending} className={`${btn} bg-foreground text-background`}>
            {cancel.isPending ? 'Cancelando…' : 'Cancelar pedido'}
          </button>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  )
}
