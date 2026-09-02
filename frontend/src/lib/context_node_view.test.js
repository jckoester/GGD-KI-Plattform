import { describe, expect, it } from 'vitest'
import { einordnung, kontextknotenAnsicht } from './context_node_view.js'

const FAECHER = {
    1: { id: 1, name: 'Mathematik' },
    2: { id: 2, name: 'Chemie' },
}

// Die drei Formen, in denen Kontextknoten die Oberfläche erreichen.
const ausKnotensuche = {
    id: 'n1',
    title: 'Zahlen und Operationen',
    category: 'knowledge',
    content_type: 'ik_kompetenz',
    subject_id: 1,
    metadata: { kompetenz_nr: '3.1.1(1)', bp_version: '2016.V3' },
}
const ausVorschlagssuche = {
    node_id: 'n1',
    title: 'Zahlen und Operationen',
    category: 'knowledge',
    content_type: 'ik_kompetenz',
    subject_id: 1,
    nr: '3.1.1(1)',
    bp_version: '2016.V3',
}

describe('kontextknotenAnsicht', () => {
    it('führt die drei Herkunftsformen auf dieselbe Sicht zusammen', () => {
        expect(kontextknotenAnsicht(ausVorschlagssuche)).toEqual(
            kontextknotenAnsicht(ausKnotensuche),
        )
    })

    it('nimmt die ID, die der Knoten mitbringt', () => {
        expect(kontextknotenAnsicht({ id: 'a' }).id).toBe('a')
        expect(kontextknotenAnsicht({ node_id: 'b' }).id).toBe('b')
    })

    it('liest die Nummer aus dem Schlüssel, den der Knotentyp benutzt', () => {
        const nr = (md) => kontextknotenAnsicht({ metadata: md }).nr
        expect(nr({ kompetenz_nr: '3.1.1(1)' })).toBe('3.1.1(1)')
        expect(nr({ nr: '3.1.1' })).toBe('3.1.1')
        expect(nr({ pk_id: 'PK-2' })).toBe('PK-2')
    })

    it('kommt mit leeren und unvollständigen Knoten zurecht', () => {
        expect(kontextknotenAnsicht(undefined).id).toBeNull()
        expect(kontextknotenAnsicht({}).title).toBe('')
        expect(kontextknotenAnsicht({}).nr).toBeNull()
    })
})

describe('einordnung', () => {
    it('zeigt bei Bildungsplan-Kompetenzen das Fach, nicht den Knotentyp', () => {
        // Der eigentliche Punkt: `3.1.1(1)` sagt bereits, dass es eine IK ist —
        // aus welchem Fach, sagt sonst nichts.
        const e = einordnung(kontextknotenAnsicht(ausKnotensuche), FAECHER)
        expect(e.label).toBe('Mathematik')
    })

    it('verliert den Knotentyp dabei nicht, er wandert in den Tooltip', () => {
        const e = einordnung(kontextknotenAnsicht(ausKnotensuche), FAECHER)
        expect(e.tooltip).toBe('Mathematik — IK-Kompetenz')
    })

    it('zeigt ohne Fach den Knotentyp — dort ist er die einzige Einordnung', () => {
        const e = einordnung(
            kontextknotenAnsicht({ content_type: 'arbeitsblatt' }),
            FAECHER,
        )
        expect(e.label).toBe('Arbeitsblatt')
    })

    it('nennt den Knotentyp lesbar, nicht als Schlüssel', () => {
        const e = einordnung(kontextknotenAnsicht({ content_type: 'pk_kompetenz' }), {})
        expect(e.label).toBe('Prozessbezogene Kompetenz')
    })

    it('behält einen unbekannten Typ, statt ihn zu verschweigen', () => {
        const e = einordnung(kontextknotenAnsicht({ content_type: 'neuartig' }), {})
        expect(e.label).toBe('neuartig')
    })

    it('fällt auf den Typ zurück, solange die Fächer noch nicht geladen sind', () => {
        const ansicht = kontextknotenAnsicht(ausKnotensuche)
        expect(einordnung(ansicht, {}).label).toBe('IK-Kompetenz')
        expect(einordnung(ansicht, undefined).label).toBe('IK-Kompetenz')
    })

    it('ohne Fach und ohne Typ gibt es nichts einzuordnen', () => {
        expect(einordnung(kontextknotenAnsicht({ title: 'Notiz' }), FAECHER)).toBeNull()
    })

    it('unterscheidet Fächer mit derselben Nummer', () => {
        const mathe = einordnung(kontextknotenAnsicht(ausKnotensuche), FAECHER)
        const chemie = einordnung(
            kontextknotenAnsicht({ ...ausKnotensuche, subject_id: 2 }),
            FAECHER,
        )
        expect([mathe.label, chemie.label]).toEqual(['Mathematik', 'Chemie'])
    })
})
