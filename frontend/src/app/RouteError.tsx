import { Link, isRouteErrorResponse, useRouteError } from 'react-router'

export function NotFound() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="display text-7xl">404</h1>
        <h2 className="mt-4 text-xl font-semibold">Página não encontrada</h2>
        <p className="mt-2 text-sm text-muted-foreground">O conteúdo que você procura não existe ou foi movido.</p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center bg-primary px-6 py-3 text-xs font-bold uppercase tracking-wider text-primary-foreground"
          >
            Ir para o início
          </Link>
        </div>
      </div>
    </div>
  )
}

/** errorElement das rotas: erro de renderização/carregamento de uma página não derruba o app inteiro. */
export function RouteError() {
  const error = useRouteError()
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFound />

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="display text-2xl">Esta página não carregou</h1>
        <p className="mt-2 text-sm text-muted-foreground">Algo deu errado. Tente novamente ou volte para o início.</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => window.location.reload()}
            className="inline-flex items-center justify-center bg-primary px-6 py-3 text-xs font-bold uppercase tracking-wider text-primary-foreground"
          >
            Tentar de novo
          </button>
          <a href="/" className="inline-flex items-center justify-center border border-input px-6 py-3 text-xs font-bold uppercase tracking-wider">
            Início
          </a>
        </div>
      </div>
    </div>
  )
}
