// Ponto único de avisos da loja (sonner). Toda mensagem transitória passa por aqui:
// duração, id de dedupe e anúncio para leitor de tela ficam num lugar só.
import { createElement } from 'react'
import { toast } from 'sonner'
import { getToken } from '@/lib/session'
import { ApiError } from '@/services/http'

type Kind = 'success' | 'info' | 'warning' | 'error'

export interface NotifyAction {
  label: string
  onClick: () => void
}

export interface NotifyOptions {
  /** Mesmo id = o aviso existente é atualizado, não empilhado. Padrão: tipo + texto. */
  id?: string
  description?: string
  action?: NotifyAction
  /** Só para avisos longos (ex.: limite de tentativas). */
  duration?: number
}

const BASE_MS: Record<Kind, number> = { success: 4000, info: 4000, warning: 6000, error: 7000 }
const ACTION_MS = 8000

/** Avisos com ação (Desfazer, Ver carrinho) ficam mais tempo: dá para ler e decidir. */
export const durationFor = (kind: Kind, hasAction: boolean): number => (hasAction ? Math.max(BASE_MS[kind], ACTION_MS) : BASE_MS[kind])

export const toastId = (kind: Kind, message: string, id?: string): string => id ?? `${kind}:${message}`

function show(kind: Kind, message: string, opts: NotifyOptions = {}) {
  const { id, description, action, duration } = opts
  // O sonner anuncia tudo como polite; no erro o role="alert" interno torna o anúncio assertivo.
  const title = kind === 'error' ? createElement('span', { role: 'alert' }, message) : message
  return toast[kind](title, {
    id: toastId(kind, message, id),
    duration: duration ?? durationFor(kind, !!action),
    ...(description && { description }),
    ...(action && { action: { label: action.label, onClick: action.onClick } }),
  })
}

export const notify = {
  success: (message: string, opts?: NotifyOptions) => show('success', message, opts),
  info: (message: string, opts?: NotifyOptions) => show('info', message, opts),
  warning: (message: string, opts?: NotifyOptions) => show('warning', message, opts),
  error: (message: string, opts?: NotifyOptions) => show('error', message, opts),
}

/** Falhas que não dizem respeito a um campo: rede, servidor e limite de tentativas. */
export const isTransient = (err: unknown): boolean => err instanceof ApiError && (err.status === 0 || err.status === 429 || err.status >= 500)

/** Traduz um erro de API em aviso. `retry` só entra onde repetir a ação é seguro. */
export function notifyApiError(err: unknown, opts: { fallback?: string; retry?: () => void } = {}) {
  const { fallback = 'Não foi possível concluir. Tente novamente.', retry } = opts
  if (err instanceof ApiError) {
    // Sessão vencida: o CustomerAuthProvider já avisou (e limpou o token).
    if (err.status === 401 && !getToken()) return
    if (err.status === 429) return notify.warning('Muitas tentativas. Aguarde um instante e tente de novo.', { id: 'rate-limit' })
    if (err.status === 0 || err.status >= 500) {
      const message = err.status === 0 ? 'Sem conexão com o servidor. Tente novamente.' : 'Erro no servidor. Tente novamente em instantes.'
      return notify.error(message, { id: 'server-error', ...(retry && { action: { label: 'Tentar de novo', onClick: retry } }) })
    }
  }
  return notify.error(err instanceof Error && err.message ? err.message : fallback)
}
