import { describe, it, expect } from 'vitest'
import { abweichendeSchuelerModelle, hinweisSchuelerModelle } from './modellfreigabe.js'

const STANDARD = ['chat-schnell', 'chat-standard', 'chat-komplex']

describe('abweichendeSchuelerModelle', () => {
  it('nur Jahrgänge, nur Modelle außerhalb des Standards, Klassen natürlich geordnet', () => {
    const auswahl = {
      'jahrgang-10': new Set(['chat-standard', 'ant-sonnet']),
      'jahrgang-8': new Set(['ant-sonnet', 'mistral-large']),
      lehrkraefte: new Set(['ant-opus']),
    }
    expect(abweichendeSchuelerModelle(auswahl, STANDARD)).toEqual([
      { modell: 'ant-sonnet', klassen: ['8', '10'] },
      { modell: 'mistral-large', klassen: ['8'] },
    ])
  })

  it('nur Standard oder keine Liste: kein Hinweis', () => {
    expect(hinweisSchuelerModelle({ 'jahrgang-5': new Set(['chat-schnell']) }, STANDARD)).toBeNull()
    expect(hinweisSchuelerModelle({ 'jahrgang-5': new Set(['x']) }, [])).toBeNull()
  })

  it('der Satz nennt Modell, Klassen und die Standardmodelle', () => {
    const satz = hinweisSchuelerModelle({ 'jahrgang-9': new Set(['ant-sonnet']) }, STANDARD)
    expect(satz).toContain('ant-sonnet (Klasse 9)')
    expect(satz).toContain('chat-schnell, chat-standard, chat-komplex')
  })

  it('Namen in der Team-Liste, die die Matrix nicht zeigt, zählen nicht', () => {
    const auswahl = { 'jahrgang-5': new Set(['chat-standard', 'ollama-fallback']) }
    expect(hinweisSchuelerModelle(auswahl, STANDARD, ['chat-standard', 'ant-sonnet'])).toBeNull()
  })
})
