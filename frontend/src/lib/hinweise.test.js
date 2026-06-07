import { describe, it, expect } from 'vitest'
import { parseHinweise, serializeHinweise, extractEdgeTargets } from './hinweise.js'

const LP = '11111111-1111-1111-1111-111111111111'
const LPA = '22222222-2222-2222-2222-222222222222'
const IK = '33333333-3333-3333-3333-333333333333'

const TEXT =
    `Start @[BNE](lp:${LP}) mitte @[BNE 2: Nachhaltigkeit](lpa:${LPA}) ende #[ETH 3.1](ik:${IK})!`

describe('parseHinweise', () => {
    it('leerer Text → []', () => {
        expect(parseHinweise('')).toEqual([])
        expect(parseHinweise(null)).toEqual([])
    })

    it('zerlegt Freitext + lp/lpa/ik-Tokens korrekt', () => {
        const parts = parseHinweise(TEXT)
        expect(parts.map((p) => p.kind)).toEqual([
            'text', 'lp', 'text', 'lpa', 'text', 'ik', 'text',
        ])
        const lp = parts.find((p) => p.kind === 'lp')
        const lpa = parts.find((p) => p.kind === 'lpa')
        const ik = parts.find((p) => p.kind === 'ik')
        expect(lp).toMatchObject({ label: 'BNE', node_id: LP })
        expect(lpa).toMatchObject({ label: 'BNE 2: Nachhaltigkeit', node_id: LPA })
        expect(ik).toMatchObject({ label: 'ETH 3.1', node_id: IK })
    })

    it('lpa wird nicht fälschlich als lp interpretiert', () => {
        const parts = parseHinweise(`@[X](lpa:${LPA})`)
        expect(parts).toHaveLength(1)
        expect(parts[0].kind).toBe('lpa')
        expect(parts[0].node_id).toBe(LPA)
    })
})

describe('serializeHinweise (Round-Trip)', () => {
    it('parse → serialize ist verlustfrei', () => {
        expect(serializeHinweise(parseHinweise(TEXT))).toBe(TEXT)
    })
    it('reiner Freitext bleibt unverändert', () => {
        const plain = 'Nur Text, keine Tokens.'
        expect(serializeHinweise(parseHinweise(plain))).toBe(plain)
    })
})

describe('extractEdgeTargets', () => {
    it('liefert lp/lpa/ik getrennt', () => {
        expect(extractEdgeTargets(TEXT)).toEqual({
            lp: [LP],
            lpa: [LPA],
            ik: [IK],
        })
    })
    it('leerer Text → leere Listen', () => {
        expect(extractEdgeTargets('')).toEqual({ lp: [], lpa: [], ik: [] })
    })
})
