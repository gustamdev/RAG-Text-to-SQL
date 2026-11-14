import { useEffect } from 'react'

const BASE = 'Olist Insights'

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} — ${BASE}` : `${BASE} — análise de produtos e assistente de dados`
  }, [title])
}
