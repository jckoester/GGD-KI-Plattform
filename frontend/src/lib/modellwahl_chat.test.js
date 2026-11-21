import { describe, it, expect } from 'vitest'
import { modelleFuerAssistent, zuSendendesModell } from './modellwahl_chat.js'

const MODELLE = [
  { id: 'chat-komplex', supports_function_calling: true },
  { id: 'chat-schnell', supports_function_calling: false },
  { id: 'neu' },
]

describe('modelleFuerAssistent', () => {
  it('Schüler:innen und freier Chat: kein Wähler', () => {
    expect(modelleFuerAssistent({ istLehrkraft: false, assistent: { tool_groups: [] }, modelle: MODELLE })).toBeNull()
    expect(modelleFuerAssistent({ istLehrkraft: true, assistent: null, modelle: MODELLE })).toBeNull()
  })

  it('Assistent mit Fähigkeiten: nur ⚙ und unbekannt', () => {
    const m = modelleFuerAssistent({ istLehrkraft: true, assistent: { tool_groups: ['lesson_planning'] }, modelle: MODELLE })
    expect(m.map((x) => x.id)).toEqual(['chat-komplex', 'neu'])
  })

  it('Assistent ohne Fähigkeiten: alle', () => {
    expect(modelleFuerAssistent({ istLehrkraft: true, assistent: {}, modelle: MODELLE })).toHaveLength(3)
  })
})

describe('zuSendendesModell', () => {
  it('freier Chat: das gewählte', () => {
    expect(zuSendendesModell({ mitAssistent: false, istLehrkraft: false, frei: 'chat-schnell' })).toBe('chat-schnell')
  })
  it('mit Assistent: Lehrkraft ihres, leer heißt der Server entscheidet', () => {
    expect(zuSendendesModell({ mitAssistent: true, istLehrkraft: true, imAssistenten: 'chat-komplex' })).toBe('chat-komplex')
    expect(zuSendendesModell({ mitAssistent: true, istLehrkraft: true, imAssistenten: '' })).toBeNull()
  })
  it('mit Assistent: Schüler:in schickt nie eins', () => {
    expect(zuSendendesModell({ mitAssistent: true, istLehrkraft: false, frei: 'x', imAssistenten: 'y' })).toBeNull()
  })
})
