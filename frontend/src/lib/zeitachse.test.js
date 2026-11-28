import { describe, expect, it } from 'vitest'
import {
  ACHSE, LUECKE, MIN_SPUR, MITTE, MOBIL, RANDSPALTE, RINNE, SCHMAL, SPUR_STANDARD, STUFENABSTAND, STUFENKOPF,
  achse, anker, bloecke, frueher, kalenderwoche, klammer, kurve, kurvenEnden, marken, mittelY, randmarken,
  rinnenTiefen, seiten, sichtbar, spalten, spurenWaehlen, stil, verbunden, wocheY,
} from './zeitachse.js'

const STUFEN = [{ stufe: 7, wochen: 38, kalenderwochen: [37, 38] }, { stufe: 8, wochen: 36 }]
const F = (id, extra = {}) => ({ id, code: `F${id}`, name: `Fach ${id}`, nur_bereich: false, ...extra })

describe('Achse (BE, Schritt 4)', () => {
  it('stapelt die Stufen mit Kopf und Abstand', () => {
    const a = achse(STUFEN, { px: 10 })
    expect(a.je[7].start).toBe(a.je[7].oben + STUFENKOPF)
    expect(a.je[8].oben).toBe(a.je[7].oben + STUFENKOPF + 380 + STUFENABSTAND)
    expect(wocheY(a, 8, 3)).toBe(a.je[8].start + 20)
    expect(wocheY(a, 9, 1)).toBeNull()
    expect(a.hoehe).toBe(a.je[8].oben + STUFENKOPF + 360 + STUFENABSTAND)
  })
  it('Kalenderwoche nur mit Kalender', () => {
    expect(kalenderwoche(STUFEN[0], 2)).toBe(38)
    expect(kalenderwoche(STUFEN[1], 2)).toBeNull()
  })
})

describe('Spuren (F4, nach Schritt 1)', () => {
  const faecher = [F(1), F(2), F(3, { nur_bereich: true }), F(4)]
  it('vorbelegt ohne Fächer nur über Bereiche, begrenzt', () => {
    const r = spurenWaehlen(faecher, { max: 2 })
    expect(r.spuren.map((f) => f.id)).toEqual([1, 2])
    expect(r.weitere.map((f) => f.id)).toEqual([3, 4])
    expect(r.bereiche).toBe(false)
  })
  it('eine Wahl gilt in ihrer Reihenfolge und schaltet Bereiche ein', () => {
    const r = spurenWaehlen(faecher, { gewaehlt: [3, 1, 99] })
    expect(r.spuren.map((f) => f.id)).toEqual([3, 1])
    expect(r.bereiche).toBe(true)
  })
  it('rechts innen zuerst, dann links, abwechselnd', () => {
    const { rechts, links } = seiten([F(1), F(2), F(3), F(4), F(5)])
    expect(rechts.map((f) => f.id)).toEqual([1, 3, 5])
    expect(links.map((f) => f.id)).toEqual([2, 4])
  })
})

describe('Spalten (F4)', () => {
  const fest = ACHSE + 2 * RANDSPALTE + RINNE + MITTE + 2 * LUECKE
  it('breit: Standardbreite, Mitte zwischen den Spuren, Ränder außen', () => {
    const r = spalten(2400, [F(1), F(2), F(3)])
    expect(r.spurBreite).toBe(SPUR_STANDARD)
    expect(r.schmal).toBe(false)
    const sp = r.spalten
    expect(sp.leitlinien.x).toBe(ACHSE)
    expect(sp[2].x).toBeLessThan(sp.rinne.x)            // links
    expect(sp[1].x).toBeGreaterThan(sp.mitte.x)          // rechts innen
    expect(sp[3].x).toBeGreaterThan(sp[1].x)             // rechts außen
    expect(sp.leitperspektiven.x).toBeGreaterThan(sp[3].x)
    expect(sp.rinne.x + RINNE).toBe(sp.mitte.x)
  })
  it('eng: schmale Spuren, und nicht mehr, als passen', () => {
    const viele = Array.from({ length: 30 }, (_, i) => F(i + 1))
    const r = spalten(1200, viele)
    expect(r.passen).toBe(Math.floor((1200 - fest) / (MIN_SPUR + LUECKE)))
    expect(r.genutzt).toHaveLength(r.passen)
    expect(r.spurBreite).toBeGreaterThanOrEqual(MIN_SPUR)
    expect(r.spurBreite).toBeLessThan(SCHMAL)
    expect(r.schmal).toBe(true)
    expect(r.breite).toBeLessThanOrEqual(1200)
  })
  it('ohne Leitlinien-Spalten mehr Platz; unter MOBIL nur die Mitte', () => {
    expect(spalten(1000, [F(1)], { leitlinien: false }).spalten.leitlinien).toBeUndefined()
    const m = spalten(MOBIL - 1, [F(1), F(2)])
    expect(m.mobil).toBe(true)
    expect(m.genutzt).toEqual([])
    expect(m.spalten.leitlinien).toBeUndefined()
  })
})

describe('Kapitel und Linien', () => {
  const a = achse(STUFEN)
  const { spalten: sp } = spalten(2400, [F(2)])
  const kapitel = [
    { id: 'm1', fach_id: 1, lage: [{ stufe: 7, von_woche: 1, bis_woche: 4, quelle: 'plan' }] },
    { id: 'm2', fach_id: 1, lage: [{ stufe: 7, von_woche: 30, bis_woche: 38, quelle: 'geschaetzt' },
      { stufe: 8, von_woche: 1, bis_woche: 2, quelle: 'geschaetzt' }] },
    { id: 'p1', fach_id: 2, lage: [{ stufe: 8, von_woche: 5, bis_woche: 9, quelle: 'entwurf' }] },
    { id: 'b1', fach_id: 3, lage: [{ stufe: 8, von_woche: 1, bis_woche: 9, quelle: 'plan' }] },  // keine Spur
    { id: 'm3', fach_id: 1, lage: [] },
  ]
  const je = bloecke(kapitel, a, sp, 1)

  it('Blöcke je Lage, nur mit Spalte und Lage', () => {
    expect(je.get('m2')).toHaveLength(2)
    expect(je.has('b1')).toBe(false)
    expect(je.has('m3')).toBe(false)
    const p = anker(je, 'p1')
    expect([p.x, p.y, p.h, p.seite]).toEqual([sp[2].x, wocheY(a, 8, 5), 5 * a.px - 3, 'rechts'])
    expect(frueher(je, 'm1', 'p1')).toBeLessThan(0)
  })
  it('S-Kurve von der Mitte zur Spur, waagerecht an den Enden', () => {
    const e = kurvenEnden(anker(je, 'm1'), anker(je, 'p1'))
    expect(e.x1).toBe(sp.mitte.x + MITTE)
    expect(e.x2).toBe(sp[2].x)
    expect(kurve(0, 0, 10, 20)).toBe('M0,0 C5,0 5,20 10,20')
    expect(mittelY({ y: 100, h: 10 })).toBe(105)
    expect(mittelY({ y: 100, h: 200 })).toBe(120)
  })
  it('Klammer endet waagerecht, in beide Richtungen', () => {
    expect(klammer(100, 10, 50, 20)).toBe('M100,10 H86 Q80,10 80,16 V44 Q80,50 86,50 H98')
    expect(klammer(100, 50, 10, 20)).toMatch(/V16 Q80,10 86,10 H98$/)
    // Bei kurzem Abstand wird der Radius kleiner
    expect(klammer(100, 10, 14, 20)).toContain('Q80,10 80,12')
  })
  it('Rinne: kurze Klammern innen, sich überdeckende auf verschiedenen Ebenen', () => {
    const t = rinnenTiefen([
      { schluessel: 'lang', y1: 0, y2: 400 },
      { schluessel: 'kurz', y1: 100, y2: 150 },
      { schluessel: 'daneben', y1: 500, y2: 520 },
    ])
    expect(t.get('kurz')).toBe(10)
    expect(t.get('daneben')).toBe(10)
    expect(t.get('lang')).toBeGreaterThan(t.get('kurz'))
    const viele = rinnenTiefen(Array.from({ length: 20 }, (_, i) => ({ schluessel: i, y1: 0, y2: 100 + i })))
    expect(Math.max(...viele.values())).toBe(RINNE - 6)
  })
})

describe('Bezüge', () => {
  const kapitelFach = new Map([['m1', 1], ['m2', 1], ['p1', 2], ['c1', 3]])
  const bezuege = [
    { typ: 'absprache', a: 'm1', b: 'p1', pruefung: { ergebnis: 'verletzt' } },
    { typ: 'kompetenz', a: 'm1', b: 'm2', eigenes_fach: true },
    { typ: 'bereich', a: 'm2', b: 'p1', eigenes_fach: false },
    { typ: 'kompetenz', a: 'm1', b: 'c1', eigenes_fach: false },
  ]
  const basis = { kapitelFach, fachId: 1, spurIds: new Set([2]) }

  it('Linienart: Absprachen breiter als Querverweise, verletzt rot', () => {
    expect(stil(bezuege[0])).toMatchObject({ breite: 3, strich: null, verletzt: true })
    expect(stil(bezuege[1])).toMatchObject({ breite: 2, strich: null })
    expect(stil(bezuege[2])).toMatchObject({ breite: 1, strich: '1 3' })
    expect(stil(bezuege[3]).breite).toBeLessThan(stil(bezuege[0]).breite)
  })
  it('ohne Auswahl nichts, mit Auswahl die des Kapitels; Bereiche und fremde Spuren nach Schalter', () => {
    expect(sichtbar(bezuege, basis)).toEqual([])
    expect(sichtbar(bezuege, { ...basis, alle: true }).map((b) => b.typ)).toEqual(['absprache', 'kompetenz'])
    expect(sichtbar(bezuege, { ...basis, gewaehlt: 'm2', bereiche: true })).toHaveLength(2)
    expect(sichtbar(bezuege, { ...basis, gewaehlt: 'm1', spurIds: new Set([2, 3]) })).toHaveLength(3)
  })
  it('verbunden und Marken', () => {
    expect([...verbunden(bezuege, 'p1')]).toEqual(['p1', 'm1'])
    expect([...verbunden(bezuege, 'p1', { bereiche: true })].sort()).toEqual(['m1', 'm2', 'p1'])
    expect(marken(bezuege, 'm1', kapitelFach)).toEqual({ fremd: 2, eigen: 1, verletzt: true })
    expect(marken(bezuege, 'm2', kapitelFach)).toEqual({ fremd: 0, eigen: 1, verletzt: false })
  })
})

describe('Randmarken (F6)', () => {
  it('nur Kapitel der Mitte, versetzt bei Überdeckung, je Spalte', () => {
    const a = achse(STUFEN)
    const { spalten: sp } = spalten(2400, [F(2)])
    const je = bloecke([
      { id: 'm1', fach_id: 1, lage: [{ stufe: 7, von_woche: 1, bis_woche: 4 }] },
      { id: 'p1', fach_id: 2, lage: [{ stufe: 7, von_woche: 1, bis_woche: 4 }] },
    ], a, sp, 1)
    const m = randmarken({
      m1: [{ art: 'lp', kuerzel: 'BNE' }, { art: 'lp', kuerzel: 'VB' }, { art: 'll', kuerzel: 'WE' }],
      p1: [{ art: 'lp', kuerzel: 'PG' }],
    }, je, sp)
    expect(m.map((x) => x.kuerzel)).toEqual(['WE', 'BNE', 'VB'])
    const [we, bne, vb] = m
    expect(we.x).toBe(sp.leitlinien.x + 4)
    expect(bne.x).toBe(sp.leitperspektiven.x + 4)
    expect(vb.y - bne.y).toBe(15)
    expect(we.y).toBe(bne.y)
  })
})

describe('Texte und Adresse (Schritt 5)', () => {
  it('Schuljahr, Fassung, Lage', async () => {
    const z = await import('./zeitachse.js')
    expect(z.naechstesSchuljahr('2026/27')).toBe('2027/28')
    expect(z.naechstesSchuljahr('2099/00')).toBe('2100/01')
    expect(z.fassungKurz('2016.V3')).toBe('V3')
    expect(z.fassungKurz('2016')).toBe('2016')
    expect(z.lageQuelleText({ plan: { status: 'active' } })).toBe('Jahresverlaufsplan')
    expect(z.lageQuelleText({ plan: { status: 'draft' } })).toContain('Entwurf')
    expect(z.lageQuelleText({ plan: null })).toContain('geschätzt')
    const je = { 7: { kalenderwochen: [37, 38, 39] }, 8: {} }
    expect(z.wochenText(je[7], 1, 3)).toBe('KW 37–39')
    expect(z.wochenText(je[8], 2, 2)).toBe('Woche 2')
    expect(z.lageText({ lage: [{ stufe: 7, von_woche: 2, bis_woche: 3, quelle: 'geschaetzt' },
      { stufe: 8, von_woche: 1, bis_woche: 2, quelle: 'geschaetzt' }] }, je)).toBe('Kl. 7, KW 38–39 und Kl. 8, Woche 1–2 (geschätzt)')
    expect(z.lageText({ lage: [] }, je)).toBe('nicht im Jahresverlaufsplan')
  })
  it('Bezüge eines Kapitels gruppiert, Art aus seiner Sicht', async () => {
    const z = await import('./zeitachse.js')
    const kapitelFach = new Map([['m7', 1], ['m8', 1], ['m9', 1], ['p8', 2]])
    const ort = { m7: 1, m8: 2, m9: 3, p8: 2 }
    const daten = {
      bezuege: [
        { typ: 'absprache', a: 'm8', b: 'p8', art: 'vorher' },
        { typ: 'kompetenz', a: 'm7', b: 'm8', eigenes_fach: true },
        { typ: 'kompetenz', a: 'm8', b: 'm9', eigenes_fach: true },
        { typ: 'bereich', a: 'm8', b: 'p8', eigenes_fach: false },
      ],
      fach_absprachen: [{ kapitel: 'm8', fach_code: 'BIO', text: 'x' }],
    }
    const r = z.bezuegeDesKapitels(daten, 'm8', { kapitelFach, vergleich: (a, b) => ort[a] - ort[b] })
    expect(r.absprachen.map((b) => [b.ander, b.art_hier])).toEqual([['p8', 'vorher']])
    expect(r.baut_auf.map((b) => b.ander)).toEqual(['m7'])
    expect(r.aufgegriffen.map((b) => b.ander)).toEqual(['m9'])
    expect(r.fremd).toEqual([])
    expect(r.fach).toHaveLength(1)
    expect(z.bezuegeDesKapitels(daten, 'p8', { kapitelFach, vergleich: () => 0, bereiche: true }).absprachen[0].art_hier).toBe('nachher')
    expect(z.bezuegeDesKapitels(daten, 'p8', { kapitelFach, vergleich: () => 0, bereiche: true }).fremd).toHaveLength(1)
  })
  it('Adresse hin und zurück, gemerkte Spuren', async () => {
    const z = await import('./zeitachse.js')
    const zustand = { fach: 'PH', kapitel: 'k1', schuljahr: null, weg: 7, stufe: 8, entwuerfe: true }
    expect(z.ausAdresse(new URLSearchParams(z.adresse(zustand)))).toEqual(zustand)
    expect(z.ausAdresse(new URLSearchParams('fach=M&weg=x')).weg).toBeNull()
    expect(z.gemerkteSpuren({ vernetzung_spuren: { 3: [5, 'x', 7] } }, 3)).toEqual([5, 7])
    expect(z.gemerkteSpuren({}, 3)).toBeNull()
  })
})

describe('Einstiege (Schritt 6)', () => {
  it('Pfad mit Kapitel, Stufe, Schuljahr nur wenn nicht das laufende, Entwürfe', async () => {
    const { vernetzungPfad } = await import('./zeitachse.js')
    expect(vernetzungPfad({ fach: 3, kapitel: 'k1', stufe: 8, entwuerfe: true }))
      .toBe('/knowledge/connections?fach=3&kapitel=k1&stufe=8&entwuerfe=1')
    expect(vernetzungPfad({ fach: 3, stufe: 9, schuljahr: '2026/27', aktuelles: '2026/27' }))
      .toBe('/knowledge/connections?fach=3&stufe=9')
    expect(vernetzungPfad({ fach: 3, stufe: 9, schuljahr: '2027/28', aktuelles: '2026/27' }))
      .toBe('/knowledge/connections?fach=3&schuljahr=2027%2F28&stufe=9')
  })
})
