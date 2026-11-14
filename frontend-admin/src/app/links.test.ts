import { describe, expect, it } from 'vitest'
import { adminProductHref, safeRedirect } from './links'

describe('safeRedirect', () => {
  it('aceita só caminhos internos', () => {
    expect(safeRedirect('/produtos/abc')).toBe('/produtos/abc')
    expect(safeRedirect('/produtos?q=bed')).toBe('/produtos?q=bed')
  })

  it('rejeita URLs externas, protocolo relativo, barra invertida e vazio', () => {
    for (const bad of ['//evil.com', '/\\evil.com', 'http://evil.com', 'produtos', '', null, undefined]) {
      expect(safeRedirect(bad)).toBeNull()
    }
  })

  it('não volta para o login', () => {
    expect(safeRedirect('/login')).toBeNull()
    expect(safeRedirect('/login?redirect=/')).toBeNull()
  })
})

it('adminProductHref escapa o id', () => {
  expect(adminProductHref('a/b c')).toBe('/produtos/a%2Fb%20c')
})
