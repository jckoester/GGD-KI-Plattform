import { describe, it, expect } from 'vitest'
import { parseHinweise, serializeHinweise, extractEdgeTargets, getActiveTrigger, leitlinienAuswahl, lfdbAuswahl, lfdbAnzeige } from './hinweise.js'

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
            lb: [],
            lba: [],
            ik: [IK],
        })
    })
    it('leerer Text → leere Listen', () => {
        expect(extractEdgeTargets('')).toEqual({ lp: [], lpa: [], lb: [], lba: [], ik: [] })
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

// ── Leitlinien der Schule (0.50, AT) ────────────────────────────────────────

const LB = '44444444-4444-4444-4444-444444444444'
const LBA = '55555555-5555-5555-5555-555555555555'

describe('Leitlinien-Token lb/lba', () => {
    const text = `Bezug @[Nachhaltigkeitsziele](lb:${LB}) und @[SDG13: Klimaschutz](lba:${LBA}).`

    it('zerlegt lb und lba, ohne sie mit lp/lpa zu verwechseln', () => {
        const parts = parseHinweise(text)
        expect(parts.map((p) => p.kind)).toEqual(['text', 'lb', 'text', 'lba', 'text'])
        expect(parts[1]).toMatchObject({ label: 'Nachhaltigkeitsziele', node_id: LB })
        expect(parts[3]).toMatchObject({ label: 'SDG13: Klimaschutz', node_id: LBA })
    })

    it('Round-Trip verlustfrei, auch gemischt mit LP', () => {
        const gemischt = TEXT + ' ' + text
        expect(serializeHinweise(parseHinweise(gemischt))).toBe(gemischt)
    })

    it('Kantenziele getrennt nach Art', () => {
        expect(extractEdgeTargets(text)).toMatchObject({ lb: [LB], lba: [LBA], lp: [], lpa: [] })
    })
})

describe('leitlinienAuswahl', () => {
    const nodes = [
        { id: 'a', title: 'Nachhaltigkeitsziele', content_type: 'leitbild', metadata: { kuerzel: 'SDG' } },
        { id: 'b', title: 'Weltethos', content_type: 'leitbild', metadata: { kuerzel: 'WE' } },
        { id: 'c', title: 'Klimaschutz', content_type: 'leitbild_aspekt', metadata: { kuerzel: 'SDG13', leitlinie: 'SDG' } },
        { id: 'd', title: 'Keine Armut', content_type: 'leitbild_aspekt', metadata: { kuerzel: 'SDG1', leitlinie: 'sdg' } },
        { id: 'e', title: 'Wahrhaftigkeit', content_type: 'leitbild_aspekt', metadata: { kuerzel: 'WE3', leitlinie: 'WE' } },
    ]

    it('ohne Suchwort: Köpfe nach Kürzel, Aspekte natürlich geordnet', () => {
        const items = leitlinienAuswahl(nodes, '')
        expect(items.map((i) => i.node_id)).toEqual(['a', 'd', 'c', 'b', 'e'])
        expect(items[0]).toMatchObject({ kind: 'lb', isHead: true, serialized: '@[Nachhaltigkeitsziele](lb:a)' })
        expect(items[1]).toMatchObject({ kind: 'lba', indented: true, serialized: '@[SDG1: Keine Armut](lba:d)' })
    })

    it('Suchwort im Aspekt: nur dessen Leitlinie mit dem passenden Aspekt', () => {
        expect(leitlinienAuswahl(nodes, 'klima').map((i) => i.node_id)).toEqual(['a', 'c'])
    })

    it('Suchwort im Kopf: alle Aspekte der Leitlinie', () => {
        expect(leitlinienAuswahl(nodes, 'welt').map((i) => i.node_id)).toEqual(['b', 'e'])
    })

    it('ohne Leitlinien: leer', () => {
        expect(leitlinienAuswahl([], 'x')).toEqual([])
    })
})

describe('lfdbAuswahl (0.53.1)', () => {
    const P = 'BP2016BW_ALLG_LP_LFDB'
    const n = (typ, bp, title) => ({ id: bp, content_type: typ, title, metadata: { bp_id: `${P}_${bp}` } })
    const NODES = [
        n('lfdb_kompetenz', 'B1_T1_K1', 'Was macht mich aus?'),
        n('lfdb_themenblock', 'B1_T10', 'Zehn'),
        n('lfdb_themenblock', 'B1_T1', 'Wer bin ich'),
        n('lfdb_baustein', 'B1', 'Baustein 1: Identität'),
    ]

    it('ohne Suchtext Bausteine und Themenblöcke als Baum, natürlich geordnet', () => {
        const items = lfdbAuswahl(NODES, '')
        expect(items.map((i) => [i.label, i.tiefe])).toEqual([
            ['LFDB B1: Baustein 1: Identität', 1], ['LFDB B1.T1: Wer bin ich', 2], ['LFDB B1.T10: Zehn', 2]])
        expect(items[1].serialized).toBe('@[LFDB B1.T1: Wer bin ich](lpa:B1_T1)')
        expect(items.every((i) => i.kind === 'lpa')).toBe(true)
    })

    it('mit Suchtext auch Kompetenzen, nach Titel oder Kürzel', () => {
        expect(lfdbAuswahl(NODES, 'macht').map((i) => i.label)).toEqual(['LFDB B1.T1.K1: Was macht mich aus?'])
        expect(lfdbAuswahl(NODES, 'b1.t1').map((i) => i.tiefe)).toEqual([2, 3, 2]) // T1, T1.K1, T10
    })

    it('trifft der Kopf, wie ohne Suchtext', () => {
        expect(lfdbAuswahl(NODES, 'lfdb', true)).toHaveLength(3)
    })

    it('Kurzform aus der bp_id', () => {
        expect(lfdbAnzeige(`${P}_B2_T3_K4`)).toBe('B2.T3.K4')
        expect(lfdbAnzeige('BNE_03')).toBe('')
    })
})
