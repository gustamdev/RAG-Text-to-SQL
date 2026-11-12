import { useEffect, useState } from 'react'

/** Devolve `value` só depois de ficar `delay` ms sem mudar (busca digitada → uma requisição só). */
export function useDebouncedValue<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}
