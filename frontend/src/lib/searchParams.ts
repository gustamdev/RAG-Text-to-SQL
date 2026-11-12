/** Leitura tipada de ?query params (o estado das listas vive na URL: dá para compartilhar e voltar). */

export function intParam(params: URLSearchParams, key: string, fallback: number, min = 1): number {
  const raw = params.get(key)
  if (raw === null || !/^\d+$/.test(raw)) return fallback
  return Math.max(min, Number(raw))
}

export function floatParam(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key)
  if (raw === null || raw === '') return undefined
  const value = Number(raw)
  return Number.isFinite(value) ? value : undefined
}

export function enumParam<T extends string>(
  params: URLSearchParams,
  key: string,
  allowed: readonly T[],
  fallback: T,
): T {
  const raw = params.get(key)
  return allowed.find((value) => value === raw) ?? fallback
}

/** Copia `params` aplicando mudanças: valor vazio/undefined remove a chave. */
export function withParams(
  params: URLSearchParams,
  changes: Record<string, string | number | undefined | null>,
): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const [key, value] of Object.entries(changes)) {
    if (value === undefined || value === null || value === '') next.delete(key)
    else next.set(key, String(value))
  }
  return next
}
