import { Eye, EyeOff } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useCustomer } from '@/app/customer-context'
import { InlineError } from '@/components/StateViews'
import { usePageTitle } from '@/hooks/usePageTitle'
import { safeRedirect } from '@/lib/navigation'
import { isTransient, notify, notifyApiError } from '@/lib/notify'
import { ApiError } from '@/services/http'
import { authApi, legalApi } from '@/services/shop'

const field = 'mt-1 h-11 w-full border border-input px-3 text-base'

function Shell({ title, children }: { title: string; children: ReactNode }) {
  usePageTitle(title)
  return (
    <div className="mx-auto w-full max-w-[400px] px-4 py-10">
      <h1 className="mb-6 text-2xl font-extrabold tracking-tight md:text-3xl">{title}</h1>
      {children}
    </div>
  )
}

function Password({ id, label, autoComplete, describedBy, invalid }: { id: string; label: string; autoComplete: string; describedBy?: string | undefined; invalid?: boolean }) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <label htmlFor={id} className="text-sm font-semibold">{label}</label>
      <div className="relative">
        <input id={id} name={id} type={show ? 'text' : 'password'} autoComplete={autoComplete} required maxLength={128} aria-describedby={describedBy} aria-invalid={invalid} className={`${field} pr-12`} />
        <button type="button" onClick={() => setShow(!show)} aria-pressed={show} className="absolute right-0 top-1 flex size-11 items-center justify-center">
          {show ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
          <span className="sr-only">Mostrar senha</span>
        </button>
      </div>
    </div>
  )
}

const tooMany = (err: unknown) => err instanceof ApiError && err.status === 429
const errMsg = (err: unknown, fallback: string) => (err instanceof Error && err.message ? err.message : fallback)
/** Erro de campo fica inline (leitor de tela); rede, servidor e 429 viram aviso e não duplicam o texto no formulário. */
const report = (err: unknown, fallback: string, setError: (msg: string | undefined) => void) => {
  if (isTransient(err)) { setError(undefined); notifyApiError(err) } else setError(errMsg(err, fallback))
}

const formValue = (f: FormData, k: string) => String(f.get(k) ?? '')

export function LoginPage() {
  const [params] = useSearchParams()
  const redirect = safeRedirect(params.get('redirect'))
  const navigate = useNavigate()
  const { customer } = useCustomer()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  if (customer) return <Navigate to={redirect ?? '/conta'} replace />

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    setBusy(true)
    setError(undefined)
    try {
      const email = formValue(f, 'email').trim()
      const r = await authApi.login(email, formValue(f, 'password'))
      navigate('/entrar/codigo', { state: { email, masked: r.masked_email, redirect } })
    } catch (err) {
      report(err, 'Não foi possível entrar.', setError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title="Entrar">
      <form onSubmit={submit} noValidate={false} aria-busy={busy} className="space-y-4">
        <div>
          <label htmlFor="email" className="text-sm font-semibold">E-mail</label>
          <input id="email" name="email" type="email" autoComplete="email" required className={field} />
        </div>
        <Password id="password" label="Senha" autoComplete="current-password" />
        <Link to="/esqueci-senha" className="-mt-2 flex h-11 w-fit items-center text-sm underline">Esqueci minha senha</Link>
        {error && <InlineError>{error}</InlineError>}
        <p className="text-sm text-muted-foreground">Depois da senha, enviaremos um código de 6 dígitos ao seu e-mail para concluir a entrada.</p>
        <button disabled={busy} className="btn-brand h-12 w-full text-sm disabled:opacity-50">{busy ? 'Entrando…' : 'Entrar'}</button>
      </form>
      <p className="mt-6 text-sm">Novo por aqui? <Link to="/cadastro" className="font-bold underline">Criar conta</Link></p>
    </Shell>
  )
}

export function SignupPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const password = formValue(f, 'password')
    if (password.length < 12) return setError('A senha precisa ter pelo menos 12 caracteres.')
    if (!f.get('terms') || !f.get('adult')) return setError('Aceite os termos e confirme que tem 18 anos ou mais.')
    setBusy(true)
    setError(undefined)
    try {
      const email = formValue(f, 'email').trim()
      const nickname = formValue(f, 'nickname').trim()
      // A versão vigente vem do backend (fonte única): evita o aceite falhar quando os termos mudam.
      const { version } = await legalApi.get()
      await authApi.signup({ ...(nickname && { nickname }), email, password, terms_version: version })
      navigate('/cadastro/codigo', { state: { email } })
    } catch (err) {
      report(err, 'Não foi possível criar a conta.', setError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title="Criar conta">
      <form onSubmit={submit} aria-busy={busy} className="space-y-4">
        <div>
          <label htmlFor="nickname" className="text-sm font-semibold">Apelido (opcional)</label>
          <input id="nickname" name="nickname" maxLength={40} autoComplete="nickname" className={field} />
        </div>
        <div>
          <label htmlFor="email" className="text-sm font-semibold">E-mail</label>
          <input id="email" name="email" type="email" autoComplete="email" required className={field} />
        </div>
        <Password id="password" label="Senha (mínimo 12 caracteres)" autoComplete="new-password" describedBy={error ? 'signup-err' : undefined} invalid={!!error} />
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="terms" className="mt-1 size-4" />
          <span>Li e aceito os <Link to="/termos" className="underline">Termos</Link> e a <Link to="/privacidade" className="underline">Política de Privacidade</Link>.</span></label>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="adult" className="mt-1 size-4" /><span>Tenho 18 anos ou mais.</span></label>
        {error && <InlineError id="signup-err">{error}</InlineError>}
        <button disabled={busy} className="btn-brand h-12 w-full text-sm disabled:opacity-50">{busy ? 'Enviando…' : 'Criar conta'}</button>
      </form>
      <p className="mt-6 text-sm">Já tem conta? <Link to="/entrar" className="font-bold underline">Entrar</Link></p>
    </Shell>
  )
}

function useCountdown(from = 60) {
  const [wait, setWait] = useState(from)
  useEffect(() => {
    if (wait <= 0) return
    const id = setTimeout(() => setWait((w) => w - 1), 1000)
    return () => clearTimeout(id)
  }, [wait])
  return [wait, () => setWait(from)] as const
}

const resendLabel = (wait: number) => (wait > 0 ? `Reenviar em 0:${String(wait).padStart(2, '0')}` : 'Reenviar código')

function OtpField({ code, setCode, error }: { code: string; setCode: (v: string) => void; error?: string | undefined }) {
  return (
    <div>
      <label htmlFor="otp" className="text-sm font-semibold">Código</label>
      <input
        id="otp" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code}
        onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, '').slice(0, 6))}
        aria-invalid={!!error} aria-describedby={error ? 'otp-err' : undefined}
        className={`${field} text-center font-mono text-2xl tracking-[0.5em]`}
      />
    </div>
  )
}

interface CodeState { email: string; masked?: string; redirect?: string | null }

/** OTP de 6 dígitos para login (mode=login) ou verificação de cadastro (mode=signup). */
export function CodePage({ mode }: { mode: 'login' | 'signup' }) {
  const state = useLocation().state as CodeState | null
  const navigate = useNavigate()
  const { signIn } = useCustomer()
  const [code, setCode] = useState('')
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [wait, restart] = useCountdown()

  if (!state?.email) return <Navigate to={mode === 'login' ? '/entrar' : '/cadastro'} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (code.length !== 6) return setError('Digite os 6 dígitos.')
    setBusy(true)
    setError(undefined)
    try {
      const session = await (mode === 'login' ? authApi.verifyLogin : authApi.verifySignup)(state.email, code)
      await signIn(session)
      const name = session.customer.nickname
      notify.success(`${mode === 'signup' ? 'Conta criada. ' : ''}Bem-vindo${name ? `, ${name}` : ''}`, { id: 'welcome' })
      navigate(safeRedirect(state.redirect) ?? '/', { replace: true })
    } catch (err) {
      report(err, 'Código inválido ou expirado', setError)
    } finally {
      setBusy(false)
    }
  }
  const resend = async () => {
    setError(undefined)
    try {
      await authApi.resend(state.email, mode)
      notify.success('Código reenviado. Confira seu e-mail.', { id: 'otp-resent' })
      restart()
    } catch (err) {
      if (tooMany(err)) restart()
      report(err, 'Aguarde para pedir um novo código.', setError)
    }
  }

  return (
    <Shell title="Digite o código">
      <p className="mb-4 text-sm">Digite o código de 6 dígitos que enviamos para <strong>{state.masked ?? state.email}</strong>.{import.meta.env.DEV && ' No ambiente de demonstração o código aparece no log do servidor.'}</p>
      <form onSubmit={submit} aria-busy={busy} className="space-y-4">
        <OtpField code={code} setCode={setCode} error={error} />
        {error && <InlineError id="otp-err">{error}</InlineError>}
        <button disabled={busy} className="btn-brand h-12 w-full text-sm disabled:opacity-50">{busy ? 'Verificando…' : 'Verificar'}</button>
      </form>
      <div className="mt-4 flex items-center justify-between text-sm">
        <button type="button" disabled={wait > 0} onClick={() => void resend()} className="font-bold underline disabled:no-underline disabled:opacity-50">
          {resendLabel(wait)}
        </button>
        <Link to={mode === 'login' ? '/entrar' : '/cadastro'} className="underline">Voltar</Link>
      </div>
    </Shell>
  )
}

const NEUTRAL = 'Se o e-mail estiver cadastrado, enviamos um código.'

export function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const email = formValue(new FormData(e.currentTarget), 'email').trim()
    setBusy(true)
    setError(undefined)
    try {
      const r = await authApi.forgotPassword(email)
      navigate('/redefinir-senha', { state: { email, masked: r.masked_email } })
    } catch (err) {
      report(err, 'Não foi possível enviar o código.', setError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title="Esqueci minha senha">
      <p className="mb-4 text-sm">Informe o e-mail da conta. {NEUTRAL}</p>
      <form onSubmit={submit} aria-busy={busy} className="space-y-4">
        <div>
          <label htmlFor="email" className="text-sm font-semibold">E-mail</label>
          <input id="email" name="email" type="email" autoComplete="email" required aria-invalid={!!error} aria-describedby={error ? 'forgot-err' : undefined} className={field} />
        </div>
        {error && <InlineError id="forgot-err">{error}</InlineError>}
        <button disabled={busy} className="btn-brand h-12 w-full text-sm disabled:opacity-50">{busy ? 'Enviando…' : 'Enviar código'}</button>
      </form>
      <p className="mt-6 text-sm"><Link to="/entrar" className="font-bold underline">Voltar para entrar</Link></p>
    </Shell>
  )
}

export function ResetPasswordPage() {
  const state = useLocation().state as { email: string; masked?: string } | null
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [wait, restart] = useCountdown()

  if (!state?.email) return <Navigate to="/esqueci-senha" replace />

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const password = formValue(f, 'password')
    if (code.length !== 6) return setError('Digite os 6 dígitos.')
    if (password.length < 12) return setError('A senha precisa ter pelo menos 12 caracteres.')
    if (password !== formValue(f, 'confirm')) return setError('As senhas não conferem.')
    setBusy(true)
    setError(undefined)
    try {
      await authApi.resetPassword(state.email, code, password)
      notify.success('Senha alterada. Entre com a nova senha.', { id: 'password-changed' })
      navigate('/entrar', { replace: true })
    } catch (err) {
      report(err, 'Código inválido ou expirado.', setError)
    } finally {
      setBusy(false)
    }
  }
  const resend = async () => {
    setError(undefined)
    try {
      await authApi.forgotPassword(state.email)
      notify.success('Se o e-mail estiver cadastrado, enviamos um novo código.', { id: 'otp-resent' })
      restart()
    } catch (err) {
      if (tooMany(err)) restart()
      report(err, 'Aguarde para pedir um novo código.', setError)
    }
  }

  return (
    <Shell title="Redefinir senha">
      <p className="mb-4 text-sm">{NEUTRAL} {state.masked && <>Destino: <strong>{state.masked}</strong>.</>}</p>
      <form onSubmit={submit} aria-busy={busy} className="space-y-4">
        <OtpField code={code} setCode={setCode} error={error} />
        <Password id="password" label="Nova senha (mínimo 12 caracteres)" autoComplete="new-password" describedBy={error ? 'otp-err' : undefined} invalid={!!error} />
        <Password id="confirm" label="Confirmar nova senha" autoComplete="new-password" />
        {error && <InlineError id="otp-err">{error}</InlineError>}
        <button disabled={busy} className="btn-brand h-12 w-full text-sm disabled:opacity-50">{busy ? 'Salvando…' : 'Redefinir senha'}</button>
      </form>
      <div className="mt-4 flex items-center justify-between text-sm">
        <button type="button" disabled={wait > 0} onClick={() => void resend()} className="font-bold underline disabled:no-underline disabled:opacity-50">
          {resendLabel(wait)}
        </button>
        <Link to="/entrar" className="underline">Voltar</Link>
      </div>
    </Shell>
  )
}
