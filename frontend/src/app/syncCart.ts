import type { QueryClient } from '@tanstack/react-query'
import { guestCart } from '@/lib/guestCart'
import { notify } from '@/lib/notify'
import { cartApi } from '@/services/shop'

/** Mescla o carrinho de convidado e grava o resultado no cache ANTES de `onReady` (que ativa o GET do carrinho). */
export async function syncCartOnLogin(qc: QueryClient, onReady: () => void): Promise<void> {
  const guest = guestCart.get()
  try {
    const merged = guest.length > 0 ? await cartApi.merge(guest) : await cartApi.get()
    if (guest.length > 0) guestCart.clear()
    qc.setQueryData(['cart'], merged)
    if (guest.length > 0) notify.success('Os itens do seu carrinho foram mantidos.', { id: 'cart-merged' })
  } catch {
    // falha de merge não impede o login
    void qc.invalidateQueries({ queryKey: ['cart'] })
  }
  onReady()
}
