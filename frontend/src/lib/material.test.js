import { describe, it, expect } from 'vitest'
import {
  parseMaterial, serializeMaterial, extractNodeTargets, MATERIAL_CONTENT_TYPES,
} from './material.js'
import { CONTENT_TYPES } from './taxonomy.js'

const NODE_A = '44444444-4444-4444-4444-444444444444'
const NODE_B = '55555555-5555-5555-5555-555555555555'

const TEXT = `Siehe @[Arbeitsblatt](node:${NODE_A}) und @[Video](node:${NODE_B}) sowie https://x.de`

describe('parseMaterial', () => {
    it('leerer Text → []', () => {
        expect(parseMaterial('')).toEqual([])
    })

    it('zerlegt node-Tokens und Freitext', () => {
        const parts = parseMaterial(TEXT)
        expect(parts.map((p) => p.kind)).toEqual([
            'text', 'node', 'text', 'node', 'text',
        ])
        const nodes = parts.filter((p) => p.kind === 'node')
        expect(nodes[0]).toMatchObject({ label: 'Arbeitsblatt', node_id: NODE_A })
        expect(nodes[1]).toMatchObject({ label: 'Video', node_id: NODE_B })
        // URL bleibt im Freitext-Part (wird erst beim Rendern verlinkt)
        expect(parts.at(-1).label).toContain('https://x.de')
    })
})

describe('serializeMaterial (Round-Trip)', () => {
    it('parse → serialize ist verlustfrei', () => {
        expect(serializeMaterial(parseMaterial(TEXT))).toBe(TEXT)
    })
})

describe('extractNodeTargets', () => {
    it('liefert alle node-UUIDs', () => {
        expect(extractNodeTargets(TEXT)).toEqual([NODE_A, NODE_B])
    })
    it('leerer Text → []', () => {
        expect(extractNodeTargets('')).toEqual([])
    })
})

describe('MATERIAL_CONTENT_TYPES', () => {
  // Die Liste wird aus der generierten Taxonomie abgeleitet, damit neue Dokument-,
  // Artefakt- oder Konzept-Typen automatisch auswählbar sind. Diese Tests halten die
  // *Entscheidung* fest, die dahinter steht — die Ableitung allein sagt nichts darüber,
  // was drin sein soll.

  it('enthält die typischen Unterrichtsmaterialien', () => {
    // `aufgabenblatt` ist mit AP3 in `arbeitsblatt` aufgegangen (V1) — beide waren
    // Material, die Liste ändert sich dadurch inhaltlich nicht.
    for (const typ of ['arbeitsblatt', 'aufgabe', 'praesentation',
                       'methodenblatt', 'klausur', 'lerntext', 'vokabelliste']) {
      expect(MATERIAL_CONTENT_TYPES).toContain(typ)
    }
  })

  it('enthält Konzept-Typen (Nutzerentscheidung 2026-08-08)', () => {
    // Für Fächer wie NwT oder Informatik soll im Material auf fachliche Konzepte
    // des Wissensgraphen verwiesen werden können.
    expect(MATERIAL_CONTENT_TYPES).toContain('funktion')
    expect(MATERIAL_CONTENT_TYPES).toContain('bauteil')
  })

  it('enthält keine Planungsobjekte', () => {
    // Eine Unterrichtsstunde als „Material" einer Lernsequenz zu verlinken wäre
    // begrifflich schief — sie ist das Ergebnis der Planung, nicht ihr Zubehör.
    for (const typ of ['unterrichtsstunde', 'unterrichtseinheit']) {
      expect(MATERIAL_CONTENT_TYPES).not.toContain(typ)
    }
  })

  it('enthält keine personenbezogenen Texte', () => {
    // Schülertexte und Feedback gehören nicht in ein Curriculum, das dauerhaft und
    // fachschaftsweit sichtbar ist.
    expect(MATERIAL_CONTENT_TYPES).not.toContain('schuelertext')
    expect(MATERIAL_CONTENT_TYPES).not.toContain('feedback_text')
  })

  it('enthält nichts aus der Kategorie Wissen', () => {
    // Bildungsplan, Methoden, Sozialformen und Operatoren haben eigene Auswahlfelder.
    // Zwei Wege zur selben Verknüpfung wären eine Fehlerquelle.
    for (const typ of CONTENT_TYPES.knowledge) {
      expect(MATERIAL_CONTENT_TYPES).not.toContain(typ)
    }
  })

  it('ist frei von Dubletten', () => {
    expect(new Set(MATERIAL_CONTENT_TYPES).size).toBe(MATERIAL_CONTENT_TYPES.length)
  })
})
