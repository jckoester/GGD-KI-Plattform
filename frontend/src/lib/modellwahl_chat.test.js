import { describe, it, expect } from 'vitest'
import {
  assistentMitModell, kostenMitAssistent, plant, startModellAssistent, startModellFrei, voraussichtlichesModell, vorgabeText, modelleFuerAssistent, modelleMitAssistentenKosten, zuSendendesModell,
} from './modellwahl_chat.js'

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


describe('Kosten mit Assistent', () => {
  const assistent = { token_zusatz: 1100, token_dokumente: 1000, usd_je_nachricht: 0.5, usd_dokumente: 0.1 }
  const modell = { id: 'm', usd_je_nachricht: 0.002, usd_je_eingabetoken: 1e-6 }

  it('Schätzung des Modells plus feste Token mal Eingabepreis', () => {
    const k = kostenMitAssistent(modell, assistent)
    expect(k.usd_je_nachricht).toBeCloseTo(0.002 + 1100e-6)
    expect(k.usd_dokumente).toBeCloseTo(1000e-6)
  })

  it('fehlt eine Angabe, bleibt die Zahl fehlend', () => {
    expect(kostenMitAssistent({ id: 'x', usd_je_nachricht: 0.002 }, assistent).usd_je_nachricht).toBeNull()
    expect(modelleMitAssistentenKosten([{ id: 'x' }], assistent)[0].usd_je_nachricht).toBeNull()
  })

  it('Info-Knopf: gewähltes Modell, sonst die eigene Schätzung', () => {
    expect(assistentMitModell(assistent, modell).usd_je_nachricht).toBeCloseTo(0.0031)
    expect(assistentMitModell(assistent, null)).toBe(assistent)
    expect(assistentMitModell(assistent, { id: 'x' })).toBe(assistent)
  })
})


describe('voraussichtlichesModell', () => {
  const planer = { tool_groups: ['curriculum_planning'] }
  it('Wahl im Chat geht vor', () => {
    expect(voraussichtlichesModell({ gewaehlt: 'a', assistent: planer, vorlieben: { modell_planung: 'b' } })).toBe('a')
  })
  it('Planungs-Assistent ohne Wahl: die Vorliebe', () => {
    expect(voraussichtlichesModell({ gewaehlt: '', assistent: planer, vorlieben: { modell_planung: 'b' } })).toBe('b')
  })
  it('andere Assistenten oder ohne Vorliebe: das Modell des Assistenten', () => {
    expect(voraussichtlichesModell({ gewaehlt: '', assistent: { tool_groups: ['bilder'] }, vorlieben: { modell_planung: 'b' } })).toBeNull()
    expect(voraussichtlichesModell({ gewaehlt: '', assistent: planer, vorlieben: {} })).toBeNull()
    expect(plant({ tool_groups: ['lesson_planning'] })).toBe(true)
  })
})


describe('Startwerte', () => {
  const liste = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
  it('freier Chat: Vorliebe vor Tab vor Vorgabe', () => {
    expect(startModellFrei({ vorlieben: { modell_frei: 'c' }, verfuegbar: liste, gespeichert: 'b', vorgabe: 'a' })).toBe('c')
    expect(startModellFrei({ vorlieben: { modell_frei: 'weg' }, verfuegbar: liste, gespeichert: 'b', vorgabe: 'a' })).toBe('b')
    expect(startModellFrei({ vorlieben: {}, verfuegbar: liste, vorgabe: 'a' })).toBe('a')
  })
  it('Assistent: Vorliebe nur bei Planung und nur, wenn wählbar', () => {
    const planer = { tool_groups: ['lesson_planning'] }
    expect(startModellAssistent({ assistent: planer, vorlieben: { modell_planung: 'b' }, modelle: liste })).toBe('b')
    expect(startModellAssistent({ assistent: planer, vorlieben: { modell_planung: 'x' }, modelle: liste })).toBe('')
    expect(startModellAssistent({ assistent: {}, vorlieben: { modell_planung: 'b' }, modelle: liste })).toBe('')
  })
  it('Vorgabe-Eintrag nennt das Modell des Assistenten', () => {
    expect(vorgabeText({ modell: 'chat-komplex' })).toBe('wie der Assistent (chat-komplex)')
    expect(vorgabeText(null)).toBe('wie der Assistent')
  })
})
