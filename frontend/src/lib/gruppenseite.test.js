import { describe, it, expect } from 'vitest'
import {
  REITER,
  aktiverReiter,
  gruppenImFach,
  schuelerWeiche,
  fachZielSchueler,
} from './gruppenseite.js'

const MATHE = { id: 7, subject_id: 1, name: 'Klasse 8c' }
const MATHE_2 = { id: 9, subject_id: 1, name: 'Klasse 8c Förder' }
const DEUTSCH = { id: 12, subject_id: 2, name: 'Klasse 8c' }

describe('REITER', () => {
  it('führt die Übersicht an erster Stelle', () => {
    expect(REITER[0].id).toBe('uebersicht')
  })

  it('kennt „klasse" nicht mehr', () => {
    // Der Reiter kündigte an, was der Assistenten-Editor längst kann.
    expect(REITER.map((r) => r.id)).not.toContain('klasse')
  })

  it('behält „archiv" — er wird mit den Gruppen früherer Schuljahre gefüllt', () => {
    expect(REITER.map((r) => r.id)).toContain('archiv')
  })

  it('vergibt jede Kennung nur einmal', () => {
    const ids = REITER.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('aktiverReiter', () => {
  it('gibt ohne Angabe die Übersicht', () => {
    expect(aktiverReiter(null)).toBe('uebersicht')
    expect(aktiverReiter(undefined)).toBe('uebersicht')
    expect(aktiverReiter('')).toBe('uebersicht')
  })

  it('reicht bekannte Kennungen durch', () => {
    for (const { id } of REITER) {
      expect(aktiverReiter(id)).toBe(id)
    }
  })

  it('übersetzt die alte Kennung „vorbereitung" auf die Übersicht', () => {
    // Lesezeichen aus der Zeit vor 09/2026 sollen nicht ins Leere zeigen.
    expect(aktiverReiter('vorbereitung')).toBe('uebersicht')
  })

  it('fängt unbekannte Kennungen ab, statt eine leere Seite zu zeigen', () => {
    // Der Reiter-Zustand kommt aus der URL; ohne Rückfall trifft ein Tippfehler
    // keinen Zweig und die Seite bliebe unter dem Kopf leer.
    expect(aktiverReiter('klasse')).toBe('uebersicht')
    expect(aktiverReiter('quatsch')).toBe('uebersicht')
  })
})

describe('gruppenImFach', () => {
  it('filtert nach Fach', () => {
    expect(gruppenImFach([MATHE, DEUTSCH, MATHE_2], 1)).toEqual([MATHE, MATHE_2])
  })

  it('gibt ohne Fach nichts zurück', () => {
    // Ein Fach ohne Id darf nicht versehentlich alle fachlosen Gruppen einsammeln.
    expect(gruppenImFach([MATHE, { id: 3, subject_id: null }], null)).toEqual([])
    expect(gruppenImFach([MATHE], undefined)).toEqual([])
  })

  it('verträgt eine fehlende Gruppenliste', () => {
    expect(gruppenImFach(undefined, 1)).toEqual([])
  })
})

describe('schuelerWeiche', () => {
  it('leitet bei genau einer Gruppe dorthin weiter', () => {
    expect(schuelerWeiche([MATHE, DEUTSCH], 1)).toEqual({
      art: 'weiterleiten',
      gruppe: MATHE,
    })
  })

  it('fragt bei mehreren Gruppen nach', () => {
    // Sollte nicht vorkommen; die erste stillschweigend zu nehmen machte die
    // zweite unerreichbar, ohne dass jemand es merkt.
    const ergebnis = schuelerWeiche([MATHE, MATHE_2, DEUTSCH], 1)
    expect(ergebnis.art).toBe('auswahl')
    expect(ergebnis.gruppen).toEqual([MATHE, MATHE_2])
  })

  it('meldet „keine", wenn das Fach keine eigene Gruppe hat', () => {
    expect(schuelerWeiche([DEUTSCH], 1)).toEqual({ art: 'keine' })
    expect(schuelerWeiche([], 1)).toEqual({ art: 'keine' })
  })

  it('meldet „keine", solange das Fach noch nicht geladen ist', () => {
    // Die Stores füllen sich asynchron — ohne diesen Fall liefe die Weiche
    // während des ersten Renderns auf eine Weiterleitung ins Nichts.
    expect(schuelerWeiche([MATHE], null)).toEqual({ art: 'keine' })
  })
})

describe('fachZielSchueler', () => {
  it('führt bei einer Gruppe direkt dorthin', () => {
    expect(fachZielSchueler('mathematik', [MATHE])).toBe('/subjects/mathematik/groups/7')
  })

  it('führt bei mehreren Gruppen auf die Weiche', () => {
    expect(fachZielSchueler('mathematik', [MATHE, MATHE_2])).toBe('/subjects/mathematik')
  })

  it('führt ohne Gruppe auf die Weiche, die dann erklärt', () => {
    expect(fachZielSchueler('mathematik', [])).toBe('/subjects/mathematik')
  })

  it('weicht ohne Slug in die Historie aus', () => {
    // Ein Fach ohne Slug ist nicht adressierbar; die Sidebar hielt es bisher
    // ebenso (`section.slug ? … : "/history"`).
    expect(fachZielSchueler(null, [MATHE])).toBe('/history')
  })
})
