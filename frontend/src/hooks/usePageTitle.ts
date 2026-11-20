import { useEffect } from 'react'

const BASE = 'Loja Olist'

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} — ${BASE}` : `${BASE}`
  }, [title])
}
