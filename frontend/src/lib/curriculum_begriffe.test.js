import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  CHIP_KLASSEN, NAME_LAENGE, anlegenPfad, ausTreffer, aufloesungVon, aufloesungsMap, begriffeImCurriculum,
  chipHinweis, chipText, chipZustand, enterWahl, fachmethodenImCurriculum, fachmethodenVorschlaege, kannAnlegen, mitFassung, mitName, nameSchluessel,
  namensEintrag, ohneName, ungeprueft,
} from './curriculum_begriffe.js'

const SRC = join(__dirname, '..')
const quelle = (pfad) => readFileSync(join(SRC, pfad), 'utf8')

describe('Namen', () => {
  it('Eintrag: Leerraum, Fassung nur wenn belegt, Länge wie der Server', () => {
    expect(namensEintrag('  Redox   reihe ')).toEqual({ name: 'Redox reihe' })
    expect(namensEintrag('Oxidation', ' Elektronen ')).toEqual({ name: 'Oxidation', fassung: 'Elektronen' })
    expect(namensEintrag('   ')).toBeNull()
    expect(namensEintrag('x'.repeat(NAME_LAENGE + 5)).name).toHaveLength(NAME_LAENGE)
  })

  it('Schlüssel: Groß/klein, Leerraum und Bindestrich-Varianten', () => {
    expect(nameSchluessel(' Arenium‑Ion ')).toBe(nameSchluessel('arenium-ion'))
  })

  it('keine Dubletten, Fassung macht einen neuen Eintrag', () => {
    let l = mitName([], namensEintrag('Oxidation'))
    l = mitName(l, namensEintrag('oxidation'))
    expect(l).toHaveLength(1)
    l = mitName(l, namensEintrag('Oxidation', 'Elektronen'))
    expect(l).toHaveLength(2)
    expect(mitName(l, null)).toBe(l)
  })

  it('entfernen und Fassung wählen', () => {
    const l = [{ name: 'A' }, { name: 'B' }]
    expect(ohneName(l, 0)).toEqual([{ name: 'B' }])
    expect(mitFassung(l, 1, 'neu')).toEqual([{ name: 'A' }, { name: 'B', fassung: 'neu' }])
    expect(mitFassung(l, 1, '')).toEqual([{ name: 'A' }, { name: 'B' }])
  })

  it('aus einem Suchtreffer: Titel und Fassung des Bausteins (E4)', () => {
    expect(ausTreffer({ title: 'Oxidation', metadata: { fassung: 'Elektronen' } }))
      .toEqual({ name: 'Oxidation', fassung: 'Elektronen' })
    expect(ausTreffer({ title: 'Redox', metadata: {} })).toEqual({ name: 'Redox' })
  })
})

describe('Enter', () => {
  const treffer = [{ title: 'Oxidationszahl' }, { title: 'Oxidation' }]
  it('genauer Treffer vor dem Text', () => {
    expect(enterWahl('oxidation', treffer, 0, false)).toEqual({ treffer: treffer[1] })
  })
  it('mit Pfeiltasten angesteuert', () => {
    expect(enterWahl('Oxi', treffer, 0, true)).toEqual({ treffer: treffer[0] })
  })
  it('sonst der Text, auch wenn es ihn nicht gibt', () => {
    expect(enterWahl('Oxi', treffer, 0, false)).toEqual({ text: 'Oxi' })
    expect(enterWahl('  ', treffer, 0, false)).toBeNull()
  })
  it('Fachmethoden: Titel aus `name`', () => {
    expect(enterWahl('titration', [{ name: 'Titration' }], 0, false, (t) => t.name)).toEqual({ treffer: { name: 'Titration' } })
  })
})

describe('Auflösung', () => {
  const aufl = [
    { name: 'Redox', fassung: null, zustand: 'gefunden', node_id: 'n1', titel: 'Redoxreaktion', bezugsfach: false },
    { name: 'Zelle', fassung: null, zustand: 'gefunden', node_id: 'n2', titel: 'Zelle', bezugsfach: true, fach: 'Biologie' },
    { name: 'Oxidation', fassung: null, zustand: 'mehrdeutig', kandidaten: [{ fassung: 'Sauerstoff' }, { fassung: null }] },
    { name: 'Fehlt', fassung: null, zustand: 'fehlt' },
    { name: 'Oxidation', fassung: 'Elektronen', zustand: 'gefunden', node_id: 'n3' },
  ]
  const map = aufloesungsMap(aufl)

  it('Zuordnung über Name und Fassung', () => {
    expect(aufloesungVon(map, { name: 'Oxidation' }).zustand).toBe('mehrdeutig')
    expect(aufloesungVon(map, { name: 'Oxidation', fassung: 'Elektronen' }).node_id).toBe('n3')
    expect(aufloesungVon(map, { name: 'Neu' })).toBeNull()
    expect(ungeprueft([{ name: 'Redox' }, { name: 'Neu' }], map)).toEqual([{ name: 'Neu' }])
  })

  it('Nachgereichtes ergänzt, Älteres bleibt', () => {
    const neu = aufloesungsMap([{ name: 'Fehlt', fassung: null, zustand: 'gefunden', node_id: 'n9' }], map)
    expect(aufloesungVon(neu, { name: 'Fehlt' }).zustand).toBe('gefunden')
    expect(aufloesungVon(neu, { name: 'Redox' }).node_id).toBe('n1')
  })

  it('Zustand, Text und Hinweis am Chip', () => {
    expect(chipZustand(null)).toBe('ungeprueft')
    expect(chipText({ name: 'Zelle' }, aufloesungVon(map, { name: 'Zelle' }))).toBe('Zelle · Biologie')
    expect(chipText({ name: 'Oxidation', fassung: 'Elektronen' }, null)).toBe('Oxidation (Elektronen)')
    expect(chipHinweis(aufloesungVon(map, { name: 'Oxidation' }))).toContain('Sauerstoff, ohne Fassung')
    expect(chipHinweis(aufloesungVon(map, { name: 'Fehlt' }))).toContain('Anlegen kann die Fachschaft')
    expect(chipHinweis(aufloesungVon(map, { name: 'Fehlt' }), { kannAnlegen: true })).toContain('du kannst')
  })

  it('jeder Zustand hat eine eigene Farbe, nur semantische Tokens (E5)', () => {
    const klassen = Object.values(CHIP_KLASSEN)
    expect(new Set(klassen).size).toBe(klassen.length)
    for (const k of klassen) {
      expect(k).not.toMatch(/\b(?:bg|text|border)-(?:blue|gray|base|yellow|purple)-\d/)
      // Hell- und Dunkelmodus
      expect(k).toMatch(/dark:/)
    }
    expect(CHIP_KLASSEN.fehlt).toContain('border-dashed')
  })

  it('alle Begriffe eines Curriculums', () => {
    const c = { kapitel: [{ lernsequenzen: [{ metadata: { eintraege: [{ begriffe: [{ name: 'A' }] }, {}] } }] }] }
    expect(begriffeImCurriculum(c)).toEqual([{ name: 'A' }])
    expect(begriffeImCurriculum(null)).toEqual([])
  })
})

describe('Anlegen (E6)', () => {
  it('nur Mitglieder der Fachschaft des Fachs', () => {
    const fs = [{ subject_id: 3 }]
    expect(kannAnlegen(fs, 3)).toBe(true)
    expect(kannAnlegen(fs, 4)).toBe(false)
    expect(kannAnlegen(fs, null)).toBe(false)
  })

  it('Link mit Fach, Titel und Rückweg', () => {
    const p = anlegenPfad(3, 'Säure-Base-Titration', '/knowledge/curriculum/abc')
    const url = new URL(p, 'http://x')
    expect(url.pathname).toBe('/knowledge/collections/begriff/new')
    expect(url.searchParams.get('subject_id')).toBe('3')
    expect(url.searchParams.get('titel')).toBe('Säure-Base-Titration')
    expect(url.searchParams.get('back')).toBe('/knowledge/curriculum/abc')
  })
})

describe('Verdrahtung', () => {
  it('Anlegen-Seite übernimmt den Titel', () => {
    expect(quelle('routes/(app)/knowledge/collections/[type]/new/+page.svelte'))
      .toContain('searchParams.get("titel")')
    expect(quelle('lib/components/CollectionEditor.svelte')).toContain('node?.title ?? vorgabeTitel')
  })

  it('Curriculum-Tabelle: beide Felder, im Editor und in der Leseansicht', () => {
    const t = quelle('lib/components/CurriculumTable.svelte')
    expect(t).toContain('art="begriffe"')
    expect(t).toContain('art="fachmethoden"')
    expect(t.match(/\{@render namenFelder\(eintrag\)\}/g)).toHaveLength(2)
  })

  it('Im Editor öffnet „anlegen“ einen neuen Tab — sonst gingen Änderungen verloren', () => {
    expect(quelle('lib/components/NamenChips.svelte')).toContain("target={editMode ? '_blank' : null}")
    expect(quelle('lib/components/CurriculumTable.svelte')).toContain('onvisibilitychange={beiRueckkehr}')
  })
})

describe('Fachmethoden-Vorschläge (Abnahme 15.11.2026)', () => {
  it('auch noch nicht gespeicherte aus dem offenen Editor', () => {
    const c = { kapitel: [{ lernsequenzen: [{ metadata: { eintraege: [
      { fachmethoden: [{ name: 'Analyse' }] }, { fachmethoden: [{ name: 'analyse' }, { name: 'Erörterung' }] },
    ] } }] }] }
    const lokal = fachmethodenImCurriculum(c)
    expect(lokal).toEqual(['Analyse', 'analyse', 'Erörterung'])
    // Server kennt nichts: lokal gezählt, gefiltert
    expect(fachmethodenVorschlaege([], lokal, 'ana')).toEqual([{ name: 'Analyse', anzahl: 2 }])
    // Was der Server kennt, zählt der Server — kein doppeltes Zählen
    expect(fachmethodenVorschlaege([{ name: 'Analyse', anzahl: 5 }], lokal, ''))
      .toEqual([{ name: 'Analyse', anzahl: 5 }, { name: 'Erörterung', anzahl: 1 }])
  })

  it('wer mit dem Gesuchten beginnt, zuerst', () => {
    const v = fachmethodenVorschlaege([{ name: 'Textanalyse', anzahl: 9 }], ['Analyse'], 'ana')
    expect(v.map((m) => m.name)).toEqual(['Analyse', 'Textanalyse'])
  })
})

describe('Editor (Abnahme 15.11.2026)', () => {
  const seite = quelle('routes/(app)/knowledge/curriculum/[id]/edit/+page.svelte')
  it('volle Breite wie die Jahresübersicht', () => {
    expect(seite).not.toMatch(/max-w-4xl/)
  })
  it('Knöpfe mit Icons', () => {
    expect(seite.match(/<Save class/g)).toHaveLength(2)
    expect(seite.match(/<X class/g)).toHaveLength(2)
    const tabelle = quelle('lib/components/CurriculumTable.svelte')
    expect(tabelle).not.toMatch(/\n\s*\+ (Eintrag|Neuer Eintrag|Lernsequenz|Kapitel|Erstes)/)
    expect(tabelle.match(/<Plus class/g)).toHaveLength(6)
    expect(tabelle).not.toContain('text-primary dark:text-dark-bl')
  })
})

describe('Leseansicht (Jan, 15.11.2026)', () => {
  const seite = quelle('routes/(app)/knowledge/curriculum/[id]/+page.svelte')
  it('volle Breite wie der Editor', () => {
    expect(seite).not.toMatch(/max-w-4xl/)
  })
  it('jeder Knopf mit Icon', () => {
    // Jeder Knopf der Seite trägt die Flex-Klasse für Icon + Text — und davon gibt es so viele wie Icons.
    const knoepfe = seite.match(/class="inline-flex items-center gap-1.5 px-4/g) ?? []
    const icons = seite.match(/<(?:Pencil|RefreshCw|Trash2|FileDown|X) class="w-4 h-4" \/>/g) ?? []
    expect(knoepfe).toHaveLength(17)
    expect(icons).toHaveLength(17)
    expect(seite).not.toMatch(/class="px-4 py-/)
  })
})
