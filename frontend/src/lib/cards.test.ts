import { describe, expect, it } from 'vitest'
import { cardIssue, fmtExp, isExpired, maskExp, maskPan, toCardInput, validateCard } from './cards'

const ok = { number: '4242 4242 4242 0001', holder: 'ANA', exp: '12/30', cvv: '123' }
const now = new Date(2026, 5, 15)

describe('cards', () => {
  it('valida cartão correto', () => expect(validateCard(ok, now)).toBeUndefined())
  it('barra número curto, Luhn, validade, vencido e cvv', () => {
    expect(validateCard({ ...ok, number: '4242' }, now)).toMatch(/16 dígitos/)
    expect(validateCard({ ...ok, number: '4111 1111 1111 1112' }, now)).toMatch(/inválido/)
    expect(validateCard({ ...ok, exp: '1330' }, now)).toMatch(/MM\/AA/)
    expect(validateCard({ ...ok, exp: '05/26' }, now)).toBe('Cartão vencido.')
    expect(validateCard({ ...ok, exp: '06/26' }, now)).toBeUndefined()
    expect(validateCard({ ...ok, cvv: '12' }, now)).toMatch(/CVV/)
  })
  it('detecta cartão salvo vencido (vale até o fim do mês)', () => {
    expect(isExpired({ exp_month: 5, exp_year: 2026 }, now)).toBe(true)
    expect(isExpired({ exp_month: 6, exp_year: 2026 }, now)).toBe(false)
    expect(isExpired({ exp_month: 1, exp_year: 2027 }, now)).toBe(false)
  })
  it('aponta o campo com erro', () => {
    expect(cardIssue({ ...ok, number: '4242' }, now)?.field).toBe('num')
    expect(cardIssue({ ...ok, exp: '05/26' }, now)?.field).toBe('exp')
    expect(cardIssue({ ...ok, holder: '' }, now)?.field).toBe('nm')
    expect(cardIssue({ ...ok, cvv: '1' }, now)?.field).toBe('cvv')
  })
  it('máscaras e conversão', () => {
    expect(maskPan('42424242')).toBe('4242 4242')
    expect(maskExp('1230')).toBe('12/30')
    expect(toCardInput(ok)).toEqual({ card_number: '4242424242420001', holder: 'ANA', exp_month: 12, exp_year: 2030, cvv: '123' })
    expect(fmtExp({ exp_month: 3, exp_year: 2030 })).toBe('03/30')
  })
})
