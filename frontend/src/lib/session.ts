// Token da loja em chave própria (nunca compartilhada com outro app).
const KEY = 'olist.shop.token'

export const getToken = (): string | null => localStorage.getItem(KEY)
export const setToken = (token: string) => localStorage.setItem(KEY, token)
export const clearToken = () => localStorage.removeItem(KEY)

/** Disparado pelo cliente HTTP quando a loja responde 401 com token presente. */
export const UNAUTHORIZED_EVENT = 'shop:unauthorized'
