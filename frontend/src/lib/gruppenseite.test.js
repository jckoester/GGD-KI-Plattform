import { describe, it, expect } from 'vitest'
import { REITER, aktiverReiter } from './gruppenseite.js'

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
