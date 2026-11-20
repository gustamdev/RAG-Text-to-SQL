import { useQuery } from '@tanstack/react-query'
import { useLocation } from 'react-router'
import { ErrorState, LoadingBlock } from '@/components/StateViews'
import { usePageTitle } from '@/hooks/usePageTitle'
import { legalApi } from '@/services/shop'

const TITLE = { terms: 'Termos de uso', privacy: 'Política de Privacidade' } as const

export default function LegalPage() {
  const section: keyof typeof TITLE = useLocation().pathname === '/termos' ? 'terms' : 'privacy'
  usePageTitle(TITLE[section])
  const q = useQuery({ queryKey: ['legal'], queryFn: legalApi.get, staleTime: Infinity })
  return (
    <div className="mx-auto max-w-[68ch] space-y-4 px-4 py-10 text-sm leading-relaxed">
      <h1 className="text-3xl font-extrabold tracking-tight">{TITLE[section]}</h1>
      {q.isPending && <LoadingBlock />}
      {q.isError && <ErrorState message={q.error.message} onRetry={() => void q.refetch()} />}
      {q.data && (
        <>
          <p className="text-muted-foreground">Versão {q.data.version}</p>
          <p className="whitespace-pre-line">{q.data[section]}</p>
        </>
      )}
    </div>
  )
}
