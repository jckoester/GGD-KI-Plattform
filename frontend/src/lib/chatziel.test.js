import { describe, expect, it } from 'vitest'
import { chatVorgaben, neuerChatPfad } from './chatziel.js'

const params = (s) => new URLSearchParams(s)
const STUNDE = '0f6c2a3e-8d4b-4c1a-9e7f-2b5d6a8c9e01'

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

  it('gibt den Stundenbezug mit', () => {
    expect(neuerChatPfad({ groupId: 3, stundeId: STUNDE })).toBe(
      `/chat?group_id=3&stunde_id=${STUNDE}`,
    )
  })
})

describe('chatVorgaben', () => {
  it('liest, was der Pfad mitgibt', () => {
    // ⚠️ Die eigentliche Zusage: Was die eine Seite schreibt, liest die andere. Der
    // Fehler bestand darin, dass `subject_id` von **keinem** Parameter befüllt wurde,
    // obwohl der Zustand dafür da war.
    expect(chatVorgaben(params(`subject_id=7&group_id=3&stunde_id=${STUNDE}`))).toEqual({
      subjectId: 7,
      groupId: 3,
      stundeId: STUNDE,
    })
  })

  it('geht im Kreis', () => {
    for (const ziel of [
      { subjectId: 7 }, { groupId: 3 }, { subjectId: 7, groupId: 3 },
      { groupId: 3, stundeId: STUNDE },
    ]) {
      const pfad = neuerChatPfad(ziel)
      const gelesen = chatVorgaben(params(pfad.split('?')[1] ?? ''))
      expect(gelesen).toEqual({ subjectId: null, groupId: null, stundeId: null, ...ziel })
    }
  })

  it('ohne Parameter ist nichts vorbelegt', () => {
    expect(chatVorgaben(params(''))).toEqual({ subjectId: null, groupId: null, stundeId: null })
  })

  it('Unsinn wird zu null, nicht zu NaN', () => {
    // Ein `NaN` erreichte den Server als `null` — nur dass unterwegs niemand mehr
    // wüsste, dass überhaupt etwas dastand.
    expect(chatVorgaben(params('subject_id=abc'))).toEqual({
      subjectId: null,
      groupId: null,
      stundeId: null,
    })
  })

  it('eine Stunden-Kennung, die keine ist, wird zu null', () => {
    // Der Server wiese sie mit 422 ab — erst beim Senden, nach dem Tippen.
    for (const roh of ['abc', '42', `${STUNDE}x`]) {
      expect(chatVorgaben(params(`stunde_id=${roh}`)).stundeId).toBeNull()
    }
  })
})
