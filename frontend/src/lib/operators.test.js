import { describe, it, expect } from 'vitest'
import { sortOperatorsByTitle, formatAfb } from './operators.js'

const op = (title, afb = []) => ({ title, metadata: { afb } })

describe('sortOperatorsByTitle', () => {
  it('sortiert alphabetisch nach Titel', () => {
    const sorted = sortOperatorsByTitle([op('nennen'), op('anwenden'), op('beschreiben')])
    expect(sorted.map((o) => o.title)).toEqual(['anwenden', 'beschreiben', 'nennen'])
  })

  it('sortiert Umlaute deutsch (ü≈u, nicht ans Ende)', () => {
    const sorted = sortOperatorsByTitle([op('zeigen'), op('überprüfen'), op('untersuchen')])
    // "überprüfen" (ü≈u) steht bei den u-Wörtern, vor "zeigen"
    expect(sorted.map((o) => o.title)).toEqual(['überprüfen', 'untersuchen', 'zeigen'])
  })

  it('mutiert die Eingabe nicht', () => {
    const input = [op('b'), op('a')]
    const sorted = sortOperatorsByTitle(input)
    expect(input.map((o) => o.title)).toEqual(['b', 'a'])
    expect(sorted.map((o) => o.title)).toEqual(['a', 'b'])
  })

  it('leere/undefinierte Eingabe → []', () => {
    expect(sortOperatorsByTitle([])).toEqual([])
    expect(sortOperatorsByTitle(undefined)).toEqual([])
  })

  it('fehlende Titel werfen nicht', () => {
    const sorted = sortOperatorsByTitle([{ title: 'b' }, {}, { title: 'a' }])
    expect(sorted.map((o) => o.title)).toEqual([undefined, 'a', 'b'])
  })
})

describe('formatAfb', () => {
  it('Liste → komma-getrennt', () => {
    expect(formatAfb(op('x', ['I', 'II']))).toBe('I, II')
    expect(formatAfb(op('x', ['II']))).toBe('II')
  })

  it('leer/fehlend → leerer String', () => {
    expect(formatAfb(op('x', []))).toBe('')
    expect(formatAfb({})).toBe('')
    expect(formatAfb({ metadata: {} })).toBe('')
  })

  it('String-Wert (Robustheit) → String', () => {
    expect(formatAfb({ metadata: { afb: 'III' } })).toBe('III')
  })
})
