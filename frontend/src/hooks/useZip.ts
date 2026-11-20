import { useSyncExternalStore } from 'react'

// CEP de entrega escolhido no header (só local; nunca enviado até o cliente calcular frete).
const KEY = 'olist.shop.zip'
const listeners = new Set<() => void>()

export function setZip(zip: string) {
  localStorage.setItem(KEY, zip)
  listeners.forEach((fn) => fn())
}

export function clearZip() {
  localStorage.removeItem(KEY)
  listeners.forEach((fn) => fn())
}

export function useZip(): string {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => localStorage.getItem(KEY) ?? '',
  )
}
