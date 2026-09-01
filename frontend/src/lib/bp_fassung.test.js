import { describe, it, expect } from 'vitest'
import { fassungsLabel, mehrdeutigeFassungen } from './bp_fassung.js'

const knoten = (id, nr, bpVersion, subjectId = 1) => ({
    id,
    subject_id: subjectId,
    metadata: { kompetenz_nr: nr, bp_version: bpVersion },
})

describe('fassungsLabel', () => {
    it('nennt die Fassung so, wie der Bildungsplan sie nennt', () => {
        expect(fassungsLabel('2016.V2')).toBe('V2')
        expect(fassungsLabel('2016.V3')).toBe('V3')
    })

    it('die Ausgangsfassung heißt „Basis", nicht „2016"', () => {
        expect(fassungsLabel('2016')).toBe('Basis')
    })

    it('ohne Angabe kein Label', () => {
        expect(fassungsLabel(null)).toBeNull()
        expect(fassungsLabel('')).toBeNull()
    })
})

describe('mehrdeutigeFassungen', () => {
    it('markiert beide Seiten einer Kollision', () => {
        const liste = [
            knoten('a', '3.1.1(1)', '2016.V2'),
            knoten('b', '3.1.1(1)', '2016.V3'),
        ]
        expect(mehrdeutigeFassungen(liste)).toEqual(
            new Map([['a', 'V2'], ['b', 'V3']]),
        )
    })

    it('markiert nicht, was eindeutig ist', () => {
        // Der eigentliche Punkt: Ein Hinweis an jedem Treffer wäre Rauschen. Der
        // Bildungsplan hat für die allermeisten Nummern nur eine Fassung.
        const liste = [
            knoten('a', '3.1.1(1)', '2016.V2'),
            knoten('b', '3.1.1(1)', '2016.V3'),
            knoten('c', '3.2.4(7)', '2016.V3'),
        ]
        const markiert = mehrdeutigeFassungen(liste)
        expect(markiert.has('c')).toBe(false)
        expect(markiert.size).toBe(2)
    })

    it('dieselbe Nummer in verschiedenen Fächern ist keine Fassungsfrage', () => {
        // `2.1.1` gibt es in 24 Fächern. Dass die nebeneinanderstehen, erklärt eine
        // Fassungsangabe nicht — sie würde nur in die Irre führen.
        //
        // Bewusst mit **verschiedenen** Fassungen: Während des Rollouts steht ein Fach
        // auf V3, das andere noch auf V2. Ohne das Fach im Schlüssel bekämen beide
        // einen Hinweis und sähen aus wie zwei Fassungen derselben Kompetenz. Mit
        // gleicher Fassung auf beiden Seiten würde dieser Test nichts beweisen.
        const liste = [
            knoten('a', '2.1.1', '2016.V2', 1),
            knoten('b', '2.1.1', '2016.V3', 2),
        ]
        expect(mehrdeutigeFassungen(liste).size).toBe(0)
    })

    it('gleiche Nummer und gleiche Fassung bleibt unmarkiert', () => {
        const liste = [
            knoten('a', '3.1.1(1)', '2016.V3'),
            knoten('b', '3.1.1(1)', '2016.V3'),
        ]
        expect(mehrdeutigeFassungen(liste).size).toBe(0)
    })

    it('Knoten ohne Nummer oder Fassung stören nicht', () => {
        const liste = [
            { id: 'x', metadata: {} },
            { id: 'y', metadata: { bp_version: '2016.V3' } },
            knoten('a', '3.1.1(1)', '2016.V2'),
            knoten('b', '3.1.1(1)', '2016.V3'),
        ]
        expect([...mehrdeutigeFassungen(liste).keys()].sort()).toEqual(['a', 'b'])
    })

    it('liest auch `metadata_` (Serialisierung des Backends)', () => {
        const liste = [
            { id: 'a', subject_id: 1, metadata_: { nr: '3.1.1', bp_version: '2016' } },
            { id: 'b', subject_id: 1, metadata_: { nr: '3.1.1', bp_version: '2016.V3' } },
        ]
        expect(mehrdeutigeFassungen(liste)).toEqual(
            new Map([['a', 'Basis'], ['b', 'V3']]),
        )
    })

    it('leere Eingabe', () => {
        expect(mehrdeutigeFassungen([]).size).toBe(0)
        expect(mehrdeutigeFassungen(undefined).size).toBe(0)
    })
})

describe('mehrdeutigeFassungen über Herkunftsformen hinweg', () => {
    // Die Vorschlagssuche und die angehefteten Knoten liefern `node_id` und flache
    // Felder statt `id` und Metadaten — auch dort müssen Fassungen auffallen.
    const flach = (nodeId, nr, bpVersion, subjectId = 1) => ({
        node_id: nodeId,
        subject_id: subjectId,
        nr,
        bp_version: bpVersion,
    })

    it('erkennt Kollisionen auch in der flachen Form', () => {
        const markiert = mehrdeutigeFassungen([
            flach('a', '3.1.1(1)', '2016.V2'),
            flach('b', '3.1.1(1)', '2016.V3'),
        ])
        expect(markiert).toEqual(new Map([['a', 'V2'], ['b', 'V3']]))
    })

    it('schlüsselt nach der ID, die der Knoten selbst trägt', () => {
        const markiert = mehrdeutigeFassungen([
            knoten('mit-id', '3.1.1(1)', '2016.V2'),
            flach('mit-node-id', '3.1.1(1)', '2016.V3'),
        ])
        expect([...markiert.keys()].sort()).toEqual(['mit-id', 'mit-node-id'])
    })
})

describe('Knoten ohne Kompetenznummer (Operatoren)', () => {
    // ⚠️ Der Fall, an dem die alte Fassung scheiterte: Operatoren tragen keine
    // Kompetenznummer. „nennen" gibt es in Englisch in drei Editionen — in einer
    // Trefferliste standen drei identische Zeilen „Englisch · nennen" untereinander,
    // ohne jedes Unterscheidungsmerkmal.
    const operator = (id, bp) => ({
        node_id: id,
        title: 'nennen',
        content_type: 'operator',
        subject_id: 7,
        bp_version: bp,
    })

    it('markiert gleichnamige Operatoren desselben Fachs', () => {
        const markiert = mehrdeutigeFassungen([
            operator('a', '2016'),
            operator('b', '2016.V2'),
            operator('c', '2016.V3'),
        ])
        expect([...markiert.values()]).toEqual(['Basis', 'V2', 'V3'])
    })

    it('lässt einen einzelnen Operator unmarkiert', () => {
        expect(mehrdeutigeFassungen([operator('a', '2016.V3')]).size).toBe(0)
    })

    it('trennt nach Fach', () => {
        // Dasselbe Verb in zwei Fächern ist kein Fassungsproblem — die Fächer stehen
        // ohnehin nebeneinander und erklären einander nicht.
        const markiert = mehrdeutigeFassungen([
            operator('a', '2016'),
            { ...operator('b', '2016.V3'), subject_id: 9 },
        ])
        expect(markiert.size).toBe(0)
    })

    it('unterscheidet verschiedene Titel im selben Fach', () => {
        const markiert = mehrdeutigeFassungen([
            operator('a', '2016'),
            { ...operator('b', '2016.V3'), title: 'beurteilen' },
        ])
        expect(markiert.size).toBe(0)
    })

    it('ignoriert Groß-/Kleinschreibung und Randleerzeichen', () => {
        const markiert = mehrdeutigeFassungen([
            operator('a', '2016'),
            { ...operator('b', '2016.V3'), title: '  Nennen ' },
        ])
        expect(markiert.size).toBe(2)
    })

    it('ohne Fassung bleibt alles unmarkiert', () => {
        // Nutzerknoten tragen keine BP-Fassung — sie sind keine Editionen voneinander,
        // auch wenn sie zufällig gleich heißen.
        const markiert = mehrdeutigeFassungen([
            { node_id: 'a', title: 'Merkblatt', subject_id: 7 },
            { node_id: 'b', title: 'Merkblatt', subject_id: 7 },
        ])
        expect(markiert.size).toBe(0)
    })
})
