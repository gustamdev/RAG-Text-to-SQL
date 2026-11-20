import { useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * Foto do produto (blob storage). Sem foto, ou se ela falhar ao carregar, mostra a marca do projeto
 * com o aviso de que o produto é simulado e não tem foto. Com `imageUrl` ausente o bloco é decorativo.
 */
export function ProductThumb({
  imageUrl,
  alt = '',
  className,
}: {
  imageUrl?: string | null
  alt?: string
  className?: string
}) {
  const [failed, setFailed] = useState<string | null>(null)

  if (imageUrl && failed !== imageUrl) {
    return (
      <div className={cn('relative overflow-hidden bg-muted', className)}>
        <img
          src={imageUrl}
          alt={alt}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(imageUrl)}
          className="size-full object-cover"
        />
      </div>
    )
  }

  return (
    <div
      role="img"
      aria-label="Produto simulado, sem foto"
      className={cn('@container relative flex flex-col items-center justify-center gap-2 overflow-hidden bg-muted', className)}
    >
      {/* Marca do projeto (mesmo desenho do favicon). */}
      <svg viewBox="0 0 32 32" className="size-1/3 max-w-16" aria-hidden="true">
        <rect width="32" height="32" fill="currentColor" className="text-foreground" />
        <rect x="7" y="17" width="4.5" height="8" fill="var(--background)" />
        <rect x="13.75" y="11" width="4.5" height="14" fill="var(--background)" />
        <rect x="20.5" y="6" width="4.5" height="19" fill="var(--background)" />
      </svg>
      <p className="hidden px-3 text-center text-[11px] leading-tight text-muted-foreground @[9rem]:block">
        Produto simulado · sem foto
      </p>
    </div>
  )
}
