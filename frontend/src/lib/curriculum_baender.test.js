import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { abdeckungTexte, abdeckungsPfad, anzahlCurricula, faecherFiltern, fassungTitel, sichtbareFassungen } from './curriculum_baender.js'

const c = (id, status = 'active') => ({ id, title: id, status })
const uebersicht = {
  fassungen: [
    { bp_version: '2016.V3', art: 'geltend', nicht_zugeordnet: [],
      baender: [{ schluessel: 'Klassen 5/6', curricula: [c('k5'), c('k6', 'draft')] },
                { schluessel: 'Klassen 7/8', curricula: [] }] },
    { bp_version: '2016.V4', art: 'kommend', nicht_zugeordnet: [],
      baender: [{ schluessel: 'Klassen 5/6', curricula: [] }] },
    { bp_version: '2016', art: 'aelter', nicht_zugeordnet: [c('os')],
      baender: [{ schluessel: 'Klassen 5/6', curricula: [c('alt')] }] },
  ],
  ohne_fassung: [],
}

describe('Curricula nach Fassung und Band (0.46, Schritt 8)', () => {
  it('Titel der Fassung nennt kommende und frühere', () => {
    expect(fassungTitel({ bp_version: '2016.V3', art: 'geltend' })).toBe('BP 2016.V3')
    expect(fassungTitel({ bp_version: '2016.V4', art: 'kommend' })).toBe('BP 2016.V4 · kommende Fassung')
    expect(fassungTitel({ bp_version: '2016', art: 'aelter' })).toBe('BP 2016 · frühere Fassung')
  })

  it('Pfad der Abdeckung mit Band und Entwürfen', () => {
    expect(abdeckungsPfad({ fachId: 3, fassung: '2016.V3', band: 'Klassen 12/13 (Basisfach)' }))
      .toBe('/knowledge/curricula/coverage?fach=3&fassung=2016.V3&band=Klassen+12%2F13+%28Basisfach%29')
    expect(abdeckungsPfad({ fachId: 3, fassung: '2016.V3', band: 'Klassen 5/6', entwuerfe: true }))
      .toMatch(/&entwuerfe=1$/)
  })

  it('ohne Anlegerecht nur Bänder und Fassungen mit Curricula', () => {
    const f = sichtbareFassungen(uebersicht)
    expect(f.map((x) => x.bp_version)).toEqual(['2016.V3', '2016'])
    expect(f[0].baender.map((b) => b.schluessel)).toEqual(['Klassen 5/6'])
  })

  it('mit Anlegerecht auch leere Bänder und die kommende Fassung', () => {
    const f = sichtbareFassungen(uebersicht, { leereBaender: true })
    expect(f.map((x) => x.bp_version)).toEqual(['2016.V3', '2016.V4', '2016'])
    expect(f[0].baender).toHaveLength(2)
  })

  it('zählt Curricula samt nicht zugeordneten', () => {
    expect(anzahlCurricula(uebersicht.fassungen[2])).toBe(2)
  })
})

describe('Abdeckungsseite: IK im Band, PK der Fassung (Schritte 8 und 9)', () => {
  it('IK: Bilanz und Träger mit „partiell“', () => {
    const t = abdeckungTexte({ ik: { gesamt: 5, verknuepft: 3, partiell: 1, fehlt: 1, gruppen: [] } })
    expect(t.titel).toBe('IK-Abdeckung im Band')
    expect(t.bilanz).toBe('3 von 5 IK verknüpft · 1 partiell · 1 fehlen')
    expect(t.gut).toBe('verknuepft')
    expect(t.traeger({ curricula: [{ title: 'K5', partiell: true }, { title: 'K6', partiell: false }] }))
      .toBe('K5 (partiell), K6')
  })
  it('PK: Bilanz und Lernsequenzen je Curriculum', () => {
    const t = abdeckungTexte({ pk: { gesamt: 4, gefoerdert: 3, fehlt: 1, gruppen: [] } })
    expect(t.titel).toBe('PK-Abdeckung der Fassung')
    expect(t.bilanz).toBe('3 von 4 PK gefördert · 1 ohne Lernsequenz')
    expect(t.gut).toBe('gefoerdert')
    expect(t.traeger({ curricula: [{ title: 'K5', anzahl: 1 }, { title: 'K6', anzahl: 3 }] }))
      .toBe('K5 (1 Lernsequenz), K6 (3 Lernsequenzen)')
  })
  it('Fassungspfad ohne Band', () => {
    expect(abdeckungsPfad({ fachId: 3, fassung: '2016.V3' })).toBe('/knowledge/curricula/coverage?fach=3&fassung=2016.V3')
  })
})

describe('Fächerfilter der Curricula-Seite', () => {
  const faecher = [{ id: 1, name: 'Physik' }, { id: 2, name: 'Chemie' }, { id: 3, name: 'Biologie' }]
  const anzahl = { 1: 0, 2: 3, 3: 0 }
  it('alle: eigene immer, andere nur mit Curricula; eigene zuerst', () => {
    expect(faecherFiltern(faecher, { eigene: [1], anzahl }).map((f) => f.name)).toEqual(['Physik', 'Chemie'])
  })
  it('nur eigene', () => {
    expect(faecherFiltern(faecher, { eigene: [1], filter: 'eigene', anzahl }).map((f) => f.id)).toEqual([1])
  })
  it('ein bestimmtes Fach, auch ohne Curricula', () => {
    expect(faecherFiltern(faecher, { eigene: [1], fachId: 3, anzahl }).map((f) => f.id)).toEqual([3])
  })
})

describe('Liste und Abdeckungsseite', () => {
  const liste = readFileSync(resolve(__dirname, 'components/CurriculumList.svelte'), 'utf-8')
  const seite = readFileSync(resolve(__dirname, '../routes/(app)/knowledge/curricula/coverage/+page.svelte'), 'utf-8')

  it('Liste lädt die Übersicht nach Bändern und verlinkt die IK-Abdeckung am Band', () => {
    expect(liste).toMatch(/getCurriculaNachBaendern\(/)
    expect(liste).not.toMatch(/getCurriculaBySubject/)
    expect(liste).toMatch(/abdeckungsPfad\(\{ fachId: subjectId, fassung: f\.bp_version, band: b\.schluessel \}\)/)
    expect(liste).toMatch(/<details[^>]*open=\{f\.art !== 'aelter'\}/)  // jede Fassung einklappbar, ältere zu
    expect(liste).toMatch(/abdeckungsPfad\(\{ fachId: subjectId, fassung: f\.bp_version \}\)/)  // PK am Fassungskopf
  })

  it('Abdeckungsseite: Schalter für Entwürfe und nicht zugeordnete Curricula', () => {
    expect(seite).toMatch(/getBandAbdeckung\(fachId, fassung, band, entwuerfe\)/)
    expect(seite).toMatch(/Entwürfe einbeziehen/)
    expect(seite).toMatch(/nicht_zugeordnet/)
  })

  it('Abdeckungsseite: Überschriften je Bereich, Aufzählung, PDF', () => {
    expect(seite).toMatch(/<h3 class="text-base font-semibold/)
    expect(seite).toMatch(/list-disc/)
    expect(seite).toMatch(/exportAbdeckung\(fachId, fassung, band \|\| null, \{ entwuerfe, nurLuecken \}\)/)
  })

  it('Dropdown bei „Meine Fächer“ nur mit eigenen Fächern', () => {
    const filter = readFileSync(resolve(__dirname, 'components/FaecherFilter.svelte'), 'utf-8')
    expect(filter).toMatch(/\.filter\(\(f\) => wert !== 'eigene' \|\| eigene\.includes\(f\.id\)\)/)
  })

  it('Curricula und Jahresverlaufspläne teilen den Fachfilter (0.59)', () => {
    for (const seite of ['curricula/+page.svelte', 'year-plans/+page.svelte']) {
      const text = readFileSync(resolve(__dirname, `../routes/(app)/knowledge/${seite}`), 'utf-8')
      expect(text).toContain('<FaecherFilter')
      expect(text).toContain('faecherFiltern(')
    }
  })
})
