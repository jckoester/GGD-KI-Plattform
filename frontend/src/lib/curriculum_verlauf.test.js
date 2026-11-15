import { describe, it, expect } from 'vitest'
import { kannZuruecknehmen, rueckgaengigTitel, zurueckgenommenMeldung } from './curriculum_verlauf.js'

const jetzt = new Date().toISOString()

describe('Rückgängig im Curriculum-Editor', () => {
    it('gibt es nur mit Stand', () => {
        expect(kannZuruecknehmen(null)).toBe(false)
        expect(kannZuruecknehmen({ anzahl: 0, letzter: null })).toBe(false)
        expect(kannZuruecknehmen({ anzahl: 1, letzter: { zeit: jetzt, grund: 'editor', von_mir: true } })).toBe(true)
    })
    it('nennt, von wem der Stand ist — ohne Namen', () => {
        const v = (grund, von_mir) => ({ anzahl: 1, letzter: { zeit: jetzt, grund, von_mir } })
        expect(rueckgaengigTitel(v('editor', true))).toContain('von dir')
        expect(rueckgaengigTitel(v('editor', false))).toContain('von jemand anderem')
        expect(rueckgaengigTitel(v('assistant', false))).toContain('vom Assistenten')
        expect(rueckgaengigTitel(v('editor', true), true)).toBe('Erst speichern oder abbrechen')
    })
    it('meldet, was übrig bleibt', () => {
        expect(zurueckgenommenMeldung({ zurueckgenommen: { zeit: jetzt }, anzahl: 2 })).toContain('Weitere 2')
        expect(zurueckgenommenMeldung({ zurueckgenommen: { zeit: jetzt }, anzahl: 0 })).not.toContain('Weitere')
    })
})
