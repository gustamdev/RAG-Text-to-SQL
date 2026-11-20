import { Link } from 'react-router'
import { usePageTitle } from '@/hooks/usePageTitle'

export default function AboutPage() {
  usePageTitle('Sobre esta demo')
  return (
    <div className="mx-auto max-w-[68ch] space-y-8 px-4 py-10 text-sm leading-relaxed">
      <h1 className="text-3xl font-extrabold tracking-tight">Sobre esta demo</h1>
      <section>
        <p>Esta é uma loja de demonstração. O pagamento é simulado: nenhum valor é cobrado e nenhum produto é enviado. Os produtos e preços vêm do Brazilian E-Commerce Public Dataset by Olist (licença CC BY-NC-SA 4.0, uso não comercial). O catálogo não tem fotos: as imagens são ilustrativas. O acesso é restrito a maiores de 18 anos.</p>
      </section>
      <p>
        <Link to="/termos" className="underline">Termos de uso</Link> e <Link to="/privacidade" className="underline">Política de Privacidade</Link>.
      </p>
    </div>
  )
}
