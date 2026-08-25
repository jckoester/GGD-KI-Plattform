import { describe, it, expect } from 'vitest'
import { parseHinweise, serializeHinweise, extractEdgeTargets, getActiveTrigger } from './hinweise.js'

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

describe('getActiveTrigger', () => {
    // Alle in config/subjects.yaml vergebenen Fach-Codes, nach Bauart gruppiert.
    // Die einbuchstabigen und die mit Ziffer sind der Grund für diesen Test: Das
    // frühere Muster /#[A-ZÄÖÜ]{2,6}/ hat sie stillschweigend übergangen, sodass
    // sich auf 8 von 27 Fächern gar nicht verweisen ließ.
    const FACH_CODES = {
        'ein Buchstabe': ['D', 'G', 'M'],
        'mit Ziffer': ['E1', 'F2', 'L2', 'SPA3'],
        'zwei Buchstaben': ['BK', 'CH', 'GK', 'PH', 'WI'],
        'drei Buchstaben': ['BIO', 'BNT', 'ETH', 'GEO', 'LUT', 'MUS', 'NWT', 'PSY', 'REV', 'RRK', 'SPO', 'WBS'],
        'länger': ['RISL', 'INFWFO', 'NWTBFO'],
    }

    for (const [bauart, codes] of Object.entries(FACH_CODES)) {
        for (const code of codes) {
            it(`erkennt Fach-Code (${bauart}): #${code}`, () => {
                const text = `#${code}`
                expect(getActiveTrigger(text, text.length)).toEqual({
                    kind: 'ik',
                    fachCode: code,
                    query: '',
                    matchStart: 0,
                })
            })
        }
    }

    it('trennt Fach-Code und IK-Nummer am Leerzeichen', () => {
        const text = 'Bezug: #M 3.1.1'
        expect(getActiveTrigger(text, text.length)).toEqual({
            kind: 'ik',
            fachCode: 'M',
            query: '3.1.1',
            matchStart: 7,
        })
    })

    it('greift nur links vom Cursor', () => {
        const text = '#ETH 3.1 und Text danach'
        // Cursor direkt hinter '#ETH'
        expect(getActiveTrigger(text, 4)).toMatchObject({ kind: 'ik', fachCode: 'ETH', query: '' })
        // Cursor am Ende: der Trigger ist durch den Folgetext beendet
        expect(getActiveTrigger(text, text.length)).toBeNull()
    })

    it('normaler Text löst nicht aus', () => {
        expect(getActiveTrigger('Siehe Kapitel 3', 15)).toBeNull()
        // Kleinbuchstabe nach '#': kein Fach-Code
        expect(getActiveTrigger('#eth', 4)).toBeNull()
        // Raute allein: noch kein Code
        expect(getActiveTrigger('#', 1)).toBeNull()
    })

    it('@ erkennt die Leitperspektiven-Suche', () => {
        expect(getActiveTrigger('Text @BNE', 9)).toEqual({
            kind: 'lp',
            query: 'BNE',
            matchStart: 5,
        })
        expect(getActiveTrigger('@', 1)).toEqual({ kind: 'lp', query: '', matchStart: 0 })
    })

    it('matchStart zeigt auf die Raute, damit der Ersetzungsbereich stimmt', () => {
        const text = 'Vorher #SPA3 2.1'
        const t = getActiveTrigger(text, text.length)
        expect(text.slice(t.matchStart)).toBe('#SPA3 2.1')
    })
})
