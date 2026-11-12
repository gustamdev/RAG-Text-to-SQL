export type PageItem = number | 'gap'

export function totalPages(total: number, pageSize: number): number {
  if (pageSize <= 0) return 1
  return Math.max(1, Math.ceil(total / pageSize))
}

/**
 * Janela de páginas para a paginação: sempre a primeira e a última, `siblings` vizinhas da atual
 * e "gap" onde há salto. Ex.: página 10 de 20 -> [1, 'gap', 9, 10, 11, 'gap', 20].
 */
export function pageWindow(current: number, pages: number, siblings = 1): PageItem[] {
  if (pages <= 1) return [1]
  const page = Math.min(Math.max(1, current), pages)
  // primeira + última + atual + vizinhas + 2 gaps; abaixo disso listar tudo é mais curto
  const slots = siblings * 2 + 5
  if (pages <= slots) return Array.from({ length: pages }, (_, i) => i + 1)

  const left = Math.max(page - siblings, 2)
  const right = Math.min(page + siblings, pages - 1)
  const items: PageItem[] = [1]
  if (left > 2) items.push(left === 3 ? 2 : 'gap')
  for (let p = left; p <= right; p++) items.push(p)
  if (right < pages - 1) items.push(right === pages - 2 ? pages - 1 : 'gap')
  items.push(pages)
  return items
}
