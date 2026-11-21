import { describe, expect, it } from 'vitest'
import { uebersichtZeilen } from './curriculum_freigabe.js'

const basis = {
  stunden: 54,
  ik: { gesamt: 60, verknuepft: 50, partiell: 2, fehlt: 8, fehlt_anderswo: 8 },
  fremdes_fach: 0, veraltet: 0, begriffe_fehlend: 0, begriffe_mehrdeutig: 0,
  vorgaenger: null, einheiten_umgehaengt: 0, einheiten_ohne_kapitel: [],
}

describe('uebersichtZeilen', () => {
  it('ohne Auffälliges keine Warnung, Lücken anderswo gedeckt', () => {
    const z = uebersichtZeilen(basis)
    expect(z.map((x) => x.text)).toEqual([
      '54 Stunden in den Lernsequenzen',
      '50 von 60 inhaltsbezogenen Kompetenzen verknüpft, 2 partiell, 8 nicht verknüpft (8 davon in anderen Curricula des Bands)',
    ])
    expect(z.some((x) => x.warnung)).toBe(false)
  })
  it('warnt bei Lücken, fremdem Fach, Veraltetem und Begriffen', () => {
    const z = uebersichtZeilen({ ...basis, stunden: 0, ik: { ...basis.ik, fehlt_anderswo: 3 },
      fremdes_fach: 4, veraltet: 1, begriffe_fehlend: 2, begriffe_mehrdeutig: 1 })
    expect(z.filter((x) => x.warnung)).toHaveLength(6)
  })
  it('nennt Vorgänger, Umzug und Einheiten ohne Kapitel', () => {
    const z = uebersichtZeilen({ ...basis, vorgaenger: { id: 'v', title: 'M Kl. 9' }, einheiten_umgehaengt: 3,
      einheiten_ohne_kapitel: [{ gruppe: '9a Mathe', kapitel: 'Quadratische Funktionen' }] })
    expect(z.at(-2).text).toBe('Ersetzt „M Kl. 9“ — es wird archiviert. 3 Einheiten dieses Schuljahrs wandern auf die neuen Kapitel.')
    expect(z.at(-1)).toEqual({ text: 'Eine Einheit von 9a Mathe hängt an „Quadratische Funktionen“, das es im Entwurf nicht mehr gibt — sie behält das alte Kapitel.', warnung: true })
  })
})

describe("Leitlinien der Schule (0.50)", () => {
  it("eine Zeile je Leitlinie, ohne Warnung", () => {
    const z = uebersichtZeilen({ ...basis, leitlinien: [{ kuerzel: "SDG", titel: "Nachhaltigkeitsziele", aspekte: 17, vorkommend: 3 }] })
    expect(z).toContainEqual({ text: "Nachhaltigkeitsziele: 3 von 17 Aspekten kommen vor", warnung: false })
  })
})
