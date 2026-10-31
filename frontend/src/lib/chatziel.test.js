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

  it('gibt Assistent und Frage mit — so, wie die Chatseite sie liest', () => {
    const pfad = neuerChatPfad({ stundeId: STUNDE, assistantId: 12, frage: 'Erstelle Material für „Einstieg"' })
    const p = params(pfad.split('?')[1])
    expect(p.get('assistant_id')).toBe('12')
    expect(p.get('q')).toBe('Erstelle Material für „Einstieg"')
  })

  it('Assistentenkarte auf der Gruppenseite: Assistent und Gruppe zusammen', () => {
    // Ohne `group_id` bekam ein allgemeiner Assistent (kein Fach) keinen Gruppenbezug.
    const pfad = neuerChatPfad({ assistantId: 7, groupId: 3 })
    expect(pfad).toBe('/chat?group_id=3&assistant_id=7')
    expect(chatVorgaben(params(pfad.split('?')[1])).groupId).toBe(3)
    // Ohne Gruppe (Fachseite der Lehrkraft) bleibt es beim Assistenten allein.
    expect(neuerChatPfad({ assistantId: 7, groupId: null })).toBe('/chat?assistant_id=7')
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
      faehigkeit: null,
    })
  })

  it('geht im Kreis', () => {
    for (const ziel of [
      { subjectId: 7 }, { groupId: 3 }, { subjectId: 7, groupId: 3 },
      { groupId: 3, stundeId: STUNDE }, { groupId: 3, faehigkeit: 'planning' },
    ]) {
      const pfad = neuerChatPfad(ziel)
      const gelesen = chatVorgaben(params(pfad.split('?')[1] ?? ''))
      expect(gelesen).toEqual({ subjectId: null, groupId: null, stundeId: null, faehigkeit: null, ...ziel })
    }
  })

  it('ohne Parameter ist nichts vorbelegt', () => {
    expect(chatVorgaben(params(''))).toEqual({
      subjectId: null, groupId: null, stundeId: null, faehigkeit: null,
    })
  })

  it('Unsinn wird zu null, nicht zu NaN', () => {
    // Ein `NaN` erreichte den Server als `null` — nur dass unterwegs niemand mehr
    // wüsste, dass überhaupt etwas dastand.
    expect(chatVorgaben(params('subject_id=abc'))).toEqual({
      subjectId: null,
      groupId: null,
      stundeId: null,
      faehigkeit: null,
    })
  })

  it('nur bekannte Fähigkeiten — eine andere gilt als nicht genannt', () => {
    expect(chatVorgaben(params('faehigkeit=planning')).faehigkeit).toBe('planning')
    expect(chatVorgaben(params('faehigkeit=lesson_planning')).faehigkeit).toBe('lesson_planning')
    for (const roh of ['image_generation', 'admin', '']) {
      expect(chatVorgaben(params(`faehigkeit=${roh}`)).faehigkeit).toBeNull()
    }
  })

  it('eine Stunden-Kennung, die keine ist, wird zu null', () => {
    // Der Server wiese sie mit 422 ab — erst beim Senden, nach dem Tippen.
    for (const roh of ['abc', '42', `${STUNDE}x`]) {
      expect(chatVorgaben(params(`stunde_id=${roh}`)).stundeId).toBeNull()
    }
  })
})
