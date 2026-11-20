// Cliente HTTP da loja: base /api/v1 (proxy do Vite em dev), token Bearer da loja e erros tipados.
import { UNAUTHORIZED_EVENT, getToken, clearToken } from '@/lib/session'

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly payload: unknown

  constructor(status: number, message: string, payload?: unknown) {
    super(message)
    this.payload = payload
    this.name = 'ApiError'
    this.status = status
  }
}

type Params = Record<string, string | number | undefined | null>

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  params?: Params
  signal?: AbortSignal
  headers?: Record<string, string>
  /** 401 de reautenticação (senha incorreta) não é sessão vencida: mantém o token. */
  skipAuthReset?: boolean
}

function buildUrl(path: string, params?: Params): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value))
  }
  return url.pathname + url.search
}

/** Extrai uma mensagem legível. Erros de domínio já vêm em português; os de validação do Pydantic, não. */
export function messageFrom(status: number, payload: unknown): string {
  const detail = (payload as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const msg = (detail[0] as { msg?: unknown }).msg
    if (typeof msg === 'string' && msg.startsWith('Value error, ')) return msg.slice('Value error, '.length)
    return 'Verifique os dados informados.'
  }
  if (status === 403) return 'Você não tem permissão para esta ação.'
  if (status >= 500) return 'Erro no servidor. Tente novamente em instantes.'
  return 'Não foi possível concluir a solicitação.'
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, params, signal, skipAuthReset = false } = options
  const headers: Record<string, string> = { ...options.headers }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    const init: RequestInit = { method, headers }
    if (body !== undefined) init.body = JSON.stringify(body)
    if (signal) init.signal = signal
    response = await fetch(buildUrl(path, params), init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Sem conexão com o servidor.')
  }

  if (response.status === 204) return undefined as T

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    /* corpo vazio ou não-JSON */
  }

  if (!response.ok) {
    // Sessão vencida/revogada: limpa o token; os rotas protegidas redirecionam para /entrar.
    if (response.status === 401 && token && !skipAuthReset && path !== '/shop/auth/login/verify-otp' && path !== '/shop/auth/verify-otp') {
      clearToken()
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    throw new ApiError(response.status, messageFrom(response.status, payload), payload)
  }
  return payload as T
}
