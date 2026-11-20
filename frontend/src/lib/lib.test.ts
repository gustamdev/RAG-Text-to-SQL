import { Package, Laptop, BedDouble } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { categoryIcon } from './categoryIcons'
import { brl, measure, monthLabel, num, pct, rating, weight } from './format'
import { safeRedirect } from './navigation'
import { pageWindow, totalPages } from './pagination'
import { categoryHref, isCancelable, maskZip, productHref, titleCase } from './product'
import { enumParam, floatParam, intParam, withParams } from './searchParams'

// O Intl do pt-BR separa "R$" do valor com espaço sem quebra.
const plain = (text: string) => text.replace(/ /g, ' ')

describe('safeRedirect', () => {
  it('aceita só caminhos internos', () => {
    expect(safeRedirect('/produtos/abc')).toBe('/produtos/abc')
    expect(safeRedirect('/produtos?q=bed')).toBe('/produtos?q=bed')
  })

  it('rejeita URLs externas, protocolo relativo, barra invertida e vazio', () => {
    for (const bad of ['//evil.com', '/\\evil.com', 'http://evil.com', 'https://evil.com', 'javascript:alert(1)', 'evil.com', '', null, undefined]) {
      expect(safeRedirect(bad)).toBeNull()
    }
  })

  it('não redireciona de volta para o login (evita laço)', () => {
    expect(safeRedirect('/entrar')).toBeNull()
    expect(safeRedirect('/entrar/codigo?x=1')).toBeNull()
  })
})

describe('formatação', () => {
  it('brl', () => {
    expect(plain(brl(1234.5))).toBe('R$ 1.235')
    expect(plain(brl(1234.5, { cents: true }))).toBe('R$ 1.234,50')
    expect(plain(brl(0))).toBe('R$ 0')
  })

  it('pct recebe 0–100 e trata nulo', () => {
    expect(pct(12.34)).toBe('12,3%')
    expect(pct(0)).toBe('0,0%')
    expect(pct(50, 0)).toBe('50%')
    expect(pct(null)).toBe('—')
    expect(pct(undefined)).toBe('—')
  })

  it('num e num compacto', () => {
    expect(num(1234567)).toBe('1.234.567')
    expect(plain(num(12_345, { compact: true }))).toMatch(/^12(,3)? mil$/)
    expect(plain(num(1_500_000, { compact: true }))).toBe('1,5 mi')
  })

  it('rating, measure e weight', () => {
    expect(rating(4.256)).toBe('4,3')
    expect(rating(null)).toBe('—')
    expect(plain(measure(12.5, 'cm'))).toBe('12,5 cm')
    expect(measure(null, 'cm')).toBe('—')
    expect(plain(weight(750))).toBe('750 g')
    expect(plain(weight(1500))).toBe('1,5 kg')
    expect(weight(null)).toBe('—')
  })

  it('monthLabel', () => {
    expect(monthLabel('2018-03')).toBe('mar/18')
    expect(monthLabel('2018-12')).toBe('dez/18')
    expect(monthLabel('oops')).toBe('oops')
    expect(monthLabel('2018-13')).toBe('2018-13')
  })
})

describe('helpers de produto', () => {

  it('links escapam o id', () => {
    expect(productHref('abc123')).toBe('/produtos/abc123')
    expect(productHref('a/b c')).toBe('/produtos/a%2Fb%20c')
    expect(categoryHref('cama_mesa_banho')).toBe('/c/cama_mesa_banho')
  })

  it('categoryIcon casa por palavra-chave e cai em Package', () => {
    expect(categoryIcon('cama_mesa_banho')).toBe(BedDouble)
    expect(categoryIcon('bed_bath_table')).toBe(BedDouble)
    expect(categoryIcon('informatica_acessorios')).toBe(Laptop)
    expect(categoryIcon('categoria_inexistente_xyz')).toBe(Package)
    expect(categoryIcon('sem_categoria')).toBe(Package)
    expect(categoryIcon('')).toBe(Package)
    expect(categoryIcon(undefined)).toBe(Package)
  })
})

describe('paginação', () => {
  it('totalPages', () => {
    expect(totalPages(0, 24)).toBe(1)
    expect(totalPages(24, 24)).toBe(1)
    expect(totalPages(25, 24)).toBe(2)
    expect(totalPages(100, 0)).toBe(1)
  })

  it('lista tudo quando são poucas páginas', () => {
    expect(pageWindow(1, 1)).toEqual([1])
    expect(pageWindow(3, 7)).toEqual([1, 2, 3, 4, 5, 6, 7])
  })

  it('usa "gap" nos saltos e mantém primeira e última', () => {
    expect(pageWindow(1, 20)).toEqual([1, 2, 'gap', 20])
    expect(pageWindow(10, 20)).toEqual([1, 'gap', 9, 10, 11, 'gap', 20])
    expect(pageWindow(20, 20)).toEqual([1, 'gap', 19, 20])
  })

  it('não troca um gap de uma página só por reticências', () => {
    expect(pageWindow(4, 20)).toEqual([1, 2, 3, 4, 5, 'gap', 20])
    expect(pageWindow(17, 20)).toEqual([1, 'gap', 16, 17, 18, 19, 20])
  })

  it('prende a página atual ao intervalo válido', () => {
    expect(pageWindow(99, 20)).toEqual([1, 'gap', 19, 20])
    expect(pageWindow(-5, 20)).toEqual([1, 2, 'gap', 20])
  })
})

describe('searchParams', () => {
  const p = new URLSearchParams('page=3&min=4.5&sort=rating&bad=x&neg=-2')

  it('intParam', () => {
    expect(intParam(p, 'page', 1)).toBe(3)
    expect(intParam(p, 'bad', 1)).toBe(1)
    expect(intParam(p, 'neg', 1)).toBe(1)
    expect(intParam(p, 'missing', 7)).toBe(7)
    expect(intParam(new URLSearchParams('page=0'), 'page', 1)).toBe(1)
  })

  it('floatParam e enumParam', () => {
    expect(floatParam(p, 'min')).toBe(4.5)
    expect(floatParam(p, 'bad')).toBeUndefined()
    expect(floatParam(p, 'missing')).toBeUndefined()
    expect(enumParam(p, 'sort', ['units', 'rating'] as const, 'units')).toBe('rating')
    expect(enumParam(p, 'bad', ['units', 'rating'] as const, 'units')).toBe('units')
  })

  it('withParams remove chaves vazias e não muta o original', () => {
    const base = new URLSearchParams('q=a&page=2')
    const next = withParams(base, { q: '', page: undefined, sort: 'units' })
    expect(next.toString()).toBe('sort=units')
    expect(base.toString()).toBe('q=a&page=2')
  })
})

describe('CEP', () => {
  it('máscara progressiva', () => {
    expect(maskZip('01310')).toBe('01310')
    expect(maskZip('013101')).toBe('01310-1')
    expect(maskZip('01310-100999')).toBe('01310-100')
  })
  it('titleCase', () => {
    expect(titleCase('sao paulo')).toBe('Sao Paulo')
  })
})

describe('panOk', () => {
  it('aceita cartões de teste e Luhn válido; recusa dígito trocado', async () => {
    const { panOk } = await import('./product')
    expect(panOk('4242424242420001')).toBe(true)
    expect(panOk('4242424242420002')).toBe(true)
    expect(panOk('4111111111111111')).toBe(true)
    expect(panOk('4111111111111112')).toBe(false)
    expect(panOk('')).toBe(false)
  })
})

describe('isCancelable', () => {
  it('permite created/refused/paid e bloqueia o resto', () => {
    expect(['created', 'refused', 'paid'].every(isCancelable)).toBe(true)
    expect(['shipped', 'delivered', 'canceled'].some(isCancelable)).toBe(false)
  })
})
