/**
 * Só aceita caminhos internos ("/x"), nunca URLs externas ("//x", "/\x", "http://x") vindas de ?redirect=.
 * Também recusa as telas de entrada, para não voltar para elas depois de entrar.
 */
export function safeRedirect(value: string | null | undefined): string | null {
  if (!value || !/^\/(?![/\\])/.test(value)) return null
  const path = value.split(/[?#]/)[0] ?? value
  if (/^\/(entrar|cadastro)(\/|$)/.test(path)) return null
  return value
}
