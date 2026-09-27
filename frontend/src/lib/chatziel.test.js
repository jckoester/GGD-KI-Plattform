import { describe, expect, it } from 'vitest'
import { chatVorgaben, neuerChatPfad } from './chatziel.js'

const params = (s) => new URLSearchParams(s)

describe('neuerChatPfad', () => {
  it('ohne Vorbelegung bleibt es /chat', () => {
    expect(neuerChatPfad()).toBe('/chat')
    expect(neuerChatPfad({})).toBe('/chat')
  })

  it('gibt das Fach mit', () => {
    expect(neuerChatPfad({ subjectId: 7 })).toBe('/chat?subject_id=7')
  })

  it('gibt die Gruppe mit', () => {
    expect(neuerChatPfad({ groupId: 3 })).toBe('/chat?group_id=3')
  })

  it('beides zugleich', () => {
    expect(neuerChatPfad({ subjectId: 7, groupId: 3 })).toBe(
      '/chat?subject_id=7&group_id=3',
    )
  })
})

describe('chatVorgaben', () => {
  it('liest, was der Pfad mitgibt', () => {
    // ⚠️ Die eigentliche Zusage: Was die eine Seite schreibt, liest die andere. Der
    // Fehler bestand darin, dass `subject_id` von **keinem** Parameter befüllt wurde,
    // obwohl der Zustand dafür da war.
    expect(chatVorgaben(params('subject_id=7&group_id=3'))).toEqual({
      subjectId: 7,
      groupId: 3,
    })
  })

  it('geht im Kreis', () => {
    for (const ziel of [{ subjectId: 7 }, { groupId: 3 }, { subjectId: 7, groupId: 3 }]) {
      const pfad = neuerChatPfad(ziel)
      const gelesen = chatVorgaben(params(pfad.split('?')[1] ?? ''))
      expect(gelesen).toEqual({ subjectId: null, groupId: null, ...ziel })
    }
  })

  it('ohne Parameter ist nichts vorbelegt', () => {
    expect(chatVorgaben(params(''))).toEqual({ subjectId: null, groupId: null })
  })

  it('Unsinn wird zu null, nicht zu NaN', () => {
    // Ein `NaN` erreichte den Server als `null` — nur dass unterwegs niemand mehr
    // wüsste, dass überhaupt etwas dastand.
    expect(chatVorgaben(params('subject_id=abc'))).toEqual({
      subjectId: null,
      groupId: null,
    })
  })
})
