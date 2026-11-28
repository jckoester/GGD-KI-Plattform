import { describe, expect, it } from 'vitest'
import { seiten, spurKuerzel, umbrechen, xml } from './zeitachse_svg.js'

const F = (id, code, extra = {}) => ({ id, code, name: `Fach ${code}`, color: '#3b82f6', nur_bereich: false, ...extra })
const DATEN = {
  fach: { id: 1, code: 'M', name: 'Mathematik', color: '#3b82f6' },
  faecher: [F(2, 'PH', { color: '#8b5cf6' })],
  stufen: [
    { stufe: 7, wochen: 38, kalenderwochen: Array.from({ length: 38 }, (_, i) => 37 + i), ferien: [{ name: 'Herbstferien', nach_woche: 7 }] },
    { stufe: 8, wochen: 38, kalenderwochen: null, ferien: [] },
  ],
  kapitel: [
    { id: 'm1', titel: 'Proportionale & antiproportionale <Zuordnungen>', fach_id: 1, lage: [{ stufe: 7, von_woche: 1, bis_woche: 8, quelle: 'plan' }] },
    { id: 'm2', titel: 'Lineare Funktionen', fach_id: 1, lage: [{ stufe: 8, von_woche: 1, bis_woche: 9, quelle: 'geschaetzt' }] },
    { id: 'm3', titel: 'Terme', fach_id: 1, lage: [{ stufe: 7, von_woche: 9, bis_woche: 14, quelle: 'plan' }] },
    { id: 'p1', titel: 'Dichte', fach_id: 2, lage: [{ stufe: 8, von_woche: 1, bis_woche: 4, quelle: 'entwurf' }] },
    { id: 'p2', titel: 'Kraft', fach_id: 2, lage: [{ stufe: 8, von_woche: 5, bis_woche: 9, quelle: 'entwurf' }] },
  ],
  bezuege: [],
  leitlinien: { m1: [{ art: 'lp', kuerzel: 'BNE', titel: 'BNE', aspekte: [] }] },
}
const BEZUEGE = [
  { typ: 'absprache', a: 'm2', b: 'p1', art: 'vorher', pruefung: { ergebnis: 'verletzt' }, texte: [] },
  { typ: 'kompetenz', a: 'm1', b: 'm3', eigenes_fach: true, beispiele: [] },
  { typ: 'kompetenz', a: 'm1', b: 'm2', eigenes_fach: true, beispiele: [] },   // über die Stufengrenze
]

describe('SVG der PDF-Seiten (BE, Schritt 7)', () => {
  it('maskiert Text und bricht um', () => {
    expect(xml('a & <b> "c"')).toBe('a &amp; &lt;b&gt; &quot;c&quot;')
    expect(umbrechen('eins zwei drei vier', 60, 10, 5)).toEqual(['eins zwei', 'drei vier'])
    expect(umbrechen('eins zwei drei vier', 60, 10, 1)).toEqual(['eins zwei…'])
  })
  it('Kürzel je Spurfach nach Lage', () => {
    const k = spurKuerzel(DATEN)
    expect([k.get('p1'), k.get('p2'), k.get('m1')]).toEqual(['PH 1', 'PH 2', undefined])
  })
  it('je Stufe eine Seite, nur Präsentationsattribute, Linien innerhalb der Stufe', () => {
    const s = seiten(DATEN, { kandidaten: DATEN.faecher, bezuege: BEZUEGE })
    expect(s.map((x) => x.stufe)).toEqual([7, 8])
    const [s7, s8] = s
    for (const { svg } of s) {
      expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true)
      expect(svg).not.toMatch(/<style|class=|var\(|<script|foreignObject/)
      expect(svg.match(/url\(([^)]*)\)/g).every((u) => u.startsWith('url(#'))).toBe(true)
    }
    expect(s7.svg).toContain('&amp; antiproportionale')
    expect(s7.svg).toContain('KW 37')
    expect(s7.svg).toContain('Herbstferien')
    expect(s7.svg).toContain('>BNE<')
    expect((s7.svg.match(/marker-end/g) ?? []).length).toBe(1)   // m1→m3; m1→m2 geht über die Grenze
    expect(s8.svg).toContain('Wo. 1')
    expect(s8.svg).toContain('#b3261e')                             // verletzte Absprache rot
    expect(s8.svg).toContain('fill="url(#schraffur)"')             // geschätzt
  })
  it('schmale Spuren tragen Kürzel, die Seite nennt sie', () => {
    const viele = Array.from({ length: 5 }, (_, i) => F(10 + i, `F${i}`))
    const daten = { ...DATEN, faecher: [DATEN.faecher[0], ...viele] }
    const s8 = seiten(daten, { kandidaten: daten.faecher, bezuege: BEZUEGE })[1]
    expect(s8.svg).toContain('>PH 1<')
    expect(s8.kuerzel).toEqual([{ kuerzel: 'PH 1', titel: 'Dichte' }, { kuerzel: 'PH 2', titel: 'Kraft' }])
  })
})

describe('Anfrage für das PDF', () => {
  it('Titel, Seiten mit Stufenzeile, Liste', async () => {
    const { pdfAnfrage } = await import('./zeitachse_svg.js')
    const daten = { ...DATEN, stufen: DATEN.stufen.map((s) => ({ ...s, schuljahr: '2026/27', fassung: '2016.V2', plan: null, kalender: !!s.kalenderwochen, curricula: [{}] })) }
    const a = pdfAnfrage(daten, { kandidaten: daten.faecher, bezuege: BEZUEGE, zeitraum: 'Schuljahr 2026/27' })
    expect(a.titel).toBe('Vernetzung der Fächer: Mathematik')
    expect(a.seiten.map((s) => s.titel)).toEqual([
      'Klasse 7 · 2026/27 · Bildungsplan V2 · ohne Jahresverlaufsplan: Lage geschätzt',
      'Klasse 8 · 2026/27 · Bildungsplan V2 · ohne Jahresverlaufsplan: Lage geschätzt',
    ])
    expect(a.seiten.map((s) => s.hinweise)).toEqual([[], ['ohne Kalender, nur Unterrichtswochen']])
    expect(a.liste[0].kapitel.map((k) => k.titel)).toEqual(['Proportionale & antiproportionale <Zuordnungen>', 'Terme'])
    expect(a.liste[0].kapitel[0].zeilen).toContain('Wird aufgegriffen in — Mathematik: Terme (Kl. 7, KW 45–50)')
  })
})
