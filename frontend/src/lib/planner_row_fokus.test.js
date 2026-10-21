/**
 * Themenfeld und Notiz einer Jahresplan-Zeile holen sich den Fokus (0.21, Päckchen H).
 *
 * ⚠️ Bis dahin ersetzte ein Klick den Knopf durch ein Feld **ohne** Cursor — man musste die
 * schmale Zeile ein zweites Mal treffen, und das Feld blieb offen, bis man es traf. Im
 * Browser geprüft (Firefox, 21.10.2026); hier am Quelltext festgehalten, weil die Zeile
 * ohne Browser nicht zu bedienen ist.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const zeile = readFileSync(
    join(import.meta.dirname, 'components/planner/PlannerRow.svelte'), 'utf8')

describe('PlannerRow: Felder mit Fokus', () => {
    it.each([['themaInputEl', 'input'], ['noteInputEl', 'textarea']])('%s wird gebunden und fokussiert', (name, tag) => {
        expect(zeile).toMatch(new RegExp(`<${tag}\\b[^>]*bind:this=\\{${name}\\}`, 's'))
        expect(zeile).toMatch(new RegExp(`${name}\\??\\.focus\\(\\)`))
    })

    it('Escape setzt den Text zurück, bevor das Feld verschwindet', () => {
        // Sonst speicherte `onblur` beim Entfernen des fokussierten Felds den verworfenen Text.
        expect(zeile).toContain("if (e.key === 'Escape') { themaInput = slot.thema ?? ''; editingThema = false }")
    })
})
