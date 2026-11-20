import { createContext, useContext } from 'react'
import type { AuthSession, Customer } from '@/types/shop'

export interface CustomerContextValue {
  customer: Customer | null
  /** true enquanto /me valida um token salvo. */
  loading: boolean
  signIn: (session: AuthSession) => Promise<void>
  /** `quiet`: o chamador já avisou (troca de senha, exclusão de conta). */
  signOut: (quiet?: boolean) => Promise<void>
  /** Mescla campos editados (nome/telefone) no cliente em memória. */
  updateCustomer: (patch: Partial<Customer>) => void
}

export const CustomerContext = createContext<CustomerContextValue | null>(null)

export function useCustomer(): CustomerContextValue {
  const ctx = useContext(CustomerContext)
  if (!ctx) throw new Error('useCustomer fora do CustomerAuthProvider')
  return ctx
}
