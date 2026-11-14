export const adminProductHref = (id: string) => `/produtos/${encodeURIComponent(id)}`

/**
 * Só aceita caminhos internos ("/x"), nunca URLs externas ("//x", "/\x", "http://x") vindas de ?redirect=.
 * Também recusa a tela de login, para não voltar para ela depois de entrar.
 */
export function safeRedirect(value: string | null | undefined): string | null {
  if (!value || !/^\/(?![/\\])/.test(value)) return null
  const path = value.split(/[?#]/)[0] ?? value
  if (path === '/login' || path.startsWith('/login/')) return null
  return value
}
