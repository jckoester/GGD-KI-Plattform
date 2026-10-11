import { describe, expect, it } from 'vitest'
import { einstiegsFaehigkeit, passendeAssistenten } from './assistentenwahl.js'

const ICH = 'ich-pseudo'
const KOLLEGIN = 'kollegin-pseudo'
const CHEMIE = 6
const PHYSIK = 7

const assistent = (id, name, { von = null, fach = null, faehigkeiten = ['lesson_planning'], ...rest } = {}) => ({
  id, name, created_by: von, subject_id: fach, tool_groups: faehigkeiten, ...rest,
})

const namen = (liste) => liste.map((a) => a.name)

describe('passendeAssistenten — die sechs Stufen aus F7', () => {
  const alle = [
    // gemischt übergeben — die Reihenfolge entsteht in der Funktion
    assistent(6, 'F fremd abweichend', { von: KOLLEGIN, fach: PHYSIK }),
    assistent(4, 'D fremd ohne Fach', { von: null }),
    assistent(2, 'B eigen ohne Fach', { von: ICH }),
    assistent(5, 'E eigen abweichend', { von: ICH, fach: PHYSIK }),
    assistent(3, 'C fremd passend', { von: null, fach: CHEMIE }),
    assistent(1, 'A eigen passend', { von: ICH, fach: CHEMIE }),
  ]

  it('in fester Reihenfolge', () => {
    expect(namen(passendeAssistenten(alle, 'lesson_planning', { pseudonym: ICH, fachId: CHEMIE })))
      .toEqual(['A eigen passend', 'B eigen ohne Fach', 'C fremd passend',
        'D fremd ohne Fach', 'E eigen abweichend', 'F fremd abweichend'])
  })

  it('ohne Fach der Stunde stehen alle mit Fach hinter denen ohne', () => {
    expect(namen(passendeAssistenten(alle, 'lesson_planning', { pseudonym: ICH, fachId: null })))
      .toEqual(['B eigen ohne Fach', 'D fremd ohne Fach',
        'A eigen passend', 'E eigen abweichend', 'C fremd passend', 'F fremd abweichend'])
  })
})

describe('passendeAssistenten — Einzelfälle', () => {
  it('ein geteilter mit passendem Fach steht vor dem schulweiten ohne Fach', () => {
    const liste = [
      assistent(1, 'Stundenentwurf (schulweit)', { von: null, scope: 'school' }),
      assistent(2, 'Chemie-Stunden', { von: KOLLEGIN, fach: CHEMIE, scope: 'subject_department' }),
    ]
    expect(namen(passendeAssistenten(liste, 'lesson_planning', { pseudonym: ICH, fachId: CHEMIE })))
      .toEqual(['Chemie-Stunden', 'Stundenentwurf (schulweit)'])
  })

  it('der freigegebene Assistent einer Kollegin zählt als fremd, nicht als eigen', () => {
    const liste = [
      assistent(1, 'A von der Kollegin', { von: KOLLEGIN }),
      assistent(2, 'Z mein eigener', { von: ICH }),
    ]
    expect(namen(passendeAssistenten(liste, 'lesson_planning', { pseudonym: ICH })))
      .toEqual(['Z mein eigener', 'A von der Kollegin'])
  })

  it('zwei eigene mit passendem Fach — nach Name, beide in der Auswahl', () => {
    const liste = [
      assistent(1, 'Chemie Oberstufe', { von: ICH, fach: CHEMIE }),
      assistent(2, 'Chemie Mittelstufe', { von: ICH, fach: CHEMIE }),
      assistent(3, 'Schulweit', { von: null }),
    ]
    expect(namen(passendeAssistenten(liste, 'lesson_planning', { pseudonym: ICH, fachId: CHEMIE })))
      .toEqual(['Chemie Mittelstufe', 'Chemie Oberstufe', 'Schulweit'])
  })

  it('je Fach den eigenen zuerst (Abnahmekriterium 5)', () => {
    const liste = [
      assistent(1, 'Meine Chemie', { von: ICH, fach: CHEMIE }),
      assistent(2, 'Meine NwT', { von: ICH, fach: PHYSIK }),
    ]
    expect(passendeAssistenten(liste, 'lesson_planning', { pseudonym: ICH, fachId: CHEMIE })[0].name)
      .toBe('Meine Chemie')
    expect(passendeAssistenten(liste, 'lesson_planning', { pseudonym: ICH, fachId: PHYSIK })[0].name)
      .toBe('Meine NwT')
  })

  it('die Jahresplanung wird für die Entwurfsansicht nicht gewählt', () => {
    const liste = [
      assistent(1, 'Jahresplanung', { faehigkeiten: ['planning'] }),
      assistent(2, 'Stundenentwurf', { faehigkeiten: ['lesson_planning'] }),
    ]
    expect(namen(passendeAssistenten(liste, 'lesson_planning', { pseudonym: ICH })))
      .toEqual(['Stundenentwurf'])
    expect(namen(passendeAssistenten(liste, 'planning', { pseudonym: ICH })))
      .toEqual(['Jahresplanung'])
  })

  it('ein verborgener Assistent wird für seinen Einstieg trotzdem gewählt', () => {
    // `hidden` ist Darstellung (F9) — der Einstieg wählt aus dem, was die Person benutzen darf.
    const liste = [assistent(1, 'Stundenentwurf', { visibility: 'hidden' })]
    expect(namen(passendeAssistenten(liste, 'lesson_planning', { pseudonym: ICH })))
      .toEqual(['Stundenentwurf'])
  })

  it('keine Fähigkeit → leere Liste', () => {
    expect(passendeAssistenten([assistent(1, 'Chat', { faehigkeiten: [] })], 'lesson_planning')).toEqual([])
    expect(passendeAssistenten([{ id: 1, name: 'Alt' }], 'lesson_planning')).toEqual([])
    expect(passendeAssistenten(null, 'lesson_planning')).toEqual([])
  })

  it('ohne Pseudonym ist nichts eigen', () => {
    const liste = [assistent(1, 'B', { von: null }), assistent(2, 'A', { von: ICH, fach: PHYSIK })]
    expect(namen(passendeAssistenten(liste, 'lesson_planning', { fachId: CHEMIE }))).toEqual(['B', 'A'])
  })
})

describe('einstiegsFaehigkeit', () => {
  it('Stundenbezug → Stundenplanung, sonst die genannte Fähigkeit', () => {
    expect(einstiegsFaehigkeit({ stundeId: 'x' })).toBe('lesson_planning')
    expect(einstiegsFaehigkeit({ stundeId: 'x', faehigkeit: 'planning' })).toBe('lesson_planning')
    expect(einstiegsFaehigkeit({ faehigkeit: 'planning' })).toBe('planning')
    expect(einstiegsFaehigkeit({})).toBeNull()
  })

  it('eine Gruppe allein sucht keinen Assistenten (0.15)', () => {
    // „Neuer Chat" auf der Gruppenseite: Bis 0.15 hieß „nur Gruppe" Jahresplanung — eine
    // Schüler:in hätte den Hinweis „kein Assistent verfügbar" bekommen.
    expect(einstiegsFaehigkeit({ groupId: 3 })).toBeNull()
  })
})
