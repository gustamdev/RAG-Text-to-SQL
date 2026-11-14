import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { Brand } from '@/components/layout/Brand'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { usePageTitle } from '@/hooks/usePageTitle'
import { safeRedirect } from '@/app/links'

export default function LoginPage() {
  usePageTitle('Entrar')
  const { login, user, ready } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const destination = safeRedirect(params.get('redirect')) ?? '/'
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Quem já tem sessão de admin vai direto ao destino.
  if (ready && user) return <Navigate to={destination} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!form.email.trim() || !form.password) {
      setError('Informe e-mail e senha.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await login(form.email.trim(), form.password)
      navigate(destination, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível entrar.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between px-4 md:px-8">
          <Brand />
        </div>
      </header>

      <main className="flex flex-1 items-center px-4 py-12 md:px-8">
        <form onSubmit={submit} noValidate className="mx-auto w-full max-w-sm space-y-5">
          <div>
            <p className="eyebrow text-muted-foreground">Backoffice</p>
            <h1 className="display mt-3 text-4xl">Entrar</h1>
            <p className="mt-3 text-sm text-muted-foreground">Acesso restrito a administradores.</p>
          </div>

          <div>
            <Label htmlFor="email" className="eyebrow">
              E-mail
            </Label>
            <Input
              id="email"
              className="mt-2 h-12"
              type="email"
              autoComplete="username"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
          </div>

          <div>
            <Label htmlFor="password" className="eyebrow">
              Senha
            </Label>
            <Input
              id="password"
              className="mt-2 h-12"
              type="password"
              autoComplete="current-password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />
          </div>

          {error && (
            <p role="alert" className="border border-destructive/50 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" className="h-12 w-full text-xs font-bold uppercase tracking-wider" disabled={loading}>
            {loading ? 'Entrando…' : 'Entrar'}
          </Button>
        </form>
      </main>
    </div>
  )
}
