/** Nomes de categoria vêm em snake_case do backend ("cama_mesa_banho"): formata para exibição. */
export function categoryLabel(category: string | null | undefined): string {
  const text = (category ?? '').replace(/_+/g, ' ').trim()
  if (!text || text === 'sem categoria') return 'Sem categoria'
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export const productHref = (id: string) => `/produtos/${encodeURIComponent(id)}`

/** Link do catálogo já filtrado por categoria. */
export const categoryHref = (category: string) => `/produtos?category=${encodeURIComponent(category)}`
