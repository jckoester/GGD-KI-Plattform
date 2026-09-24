/**
 * Wächter für die Kennzeichnung der Slot-Kategorien im Jahresplan.
 *
 * ⚠️ **Am Quelltext, weil es kein Logikproblem ist.** Ob eine Zeile schraffiert aussieht,
 * kann kein Test sagen — wohl aber, dass die Klasse benutzt wird und dass die beiden
 * auffälligen Kategorien sich **nicht** dieselbe Kennzeichnung teilen. Genau das wäre
 * der Fehler, den niemand bemerkt: Ausfall und Prüfung sähen gleich aus, und die Zeile
 * behauptete etwas anderes, als sie meint.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const ZEILE = readFileSync(join(SRC, "lib/components/planner/PlannerRow.svelte"), "utf8")
const CSS = readFileSync(join(SRC, "routes/layout.css"), "utf8")

describe("Prüfungsstunden im Jahresplan", () => {
    it("tragen die eigene Schraffur-Klasse", () => {
        expect(ZEILE).toMatch(/kategorie === 'pruefung'\s*\n?\s*\?\s*'planner-pruefung-band'/)
    })

    it("die Klasse ist definiert und schraffiert wirklich", () => {
        // Eine Klasse, die es nur im Markup gibt, färbt nichts.
        expect(CSS).toContain(".planner-pruefung-band {")
        const block = CSS.slice(CSS.indexOf(".planner-pruefung-band {"))
        expect(block.slice(0, block.indexOf("}"))).toContain("repeating-linear-gradient")
    })

    it("⚠️ setzt kein `color` — die Zeile trägt eigenen Text", () => {
        // Anders als `.planner-ferien-band`: Dort steht ein Wort in einer eigenen Zeile.
        // Hier liegt die Fläche hinter Thema, Einheit und Abzeichen, deren Kontrast in
        // `PlannerRow` ausdrücklich eingestellt ist.
        const block = CSS.slice(CSS.indexOf(".planner-pruefung-band {"))
        expect(block.slice(0, block.indexOf("}"))).not.toMatch(/^\s*color:/m)
    })

    it("⚠️ unterscheidet sich von der Ausfall-Kennzeichnung", () => {
        // Ausfall ist gedämpft und grau schraffiert, Prüfung rot und nicht gedämpft.
        // Teilten sie sich eine Kennzeichnung, wäre die Zeile mehrdeutig.
        const ausfall = ZEILE.slice(ZEILE.indexOf("slot.kategorie === 'ausfall'"))
        expect(ausfall.slice(0, ausfall.indexOf("pruefung"))).not.toContain(
            "planner-pruefung-band",
        )
    })

    it("hat helle und dunkle Werte", () => {
        // Ohne den Dunkelmodus-Block stünde rote Schraffur auf dunklem Grund.
        //
        // ⚠️ **Der erste Entwurf dieses Tests war wertlos.** Er nahm `CSS.slice(indexOf
        // (".dark {"))` — also alles bis Dateiende — und fand `var(--planner-pruefung-
        // stripe)` in der Klasse *unterhalb* des Blocks. Die Gegenprobe (Dunkelwert
        // gelöscht) kam grün. Geprüft wird jetzt der **Block** und die **Deklaration**,
        // nicht irgendein Vorkommen des Namens.
        // Am Zeilenanfang suchen: `html.dark {` steht weiter oben und enthält dieselbe
        // Zeichenfolge — `indexOf(".dark {")` fand dessen Block und damit die Variablen
        // nicht. (Zweiter Anlauf desselben Fehlers in diesem Test.)
        const start = CSS.indexOf("\n.dark {")
        expect(start, "Der Dunkelmodus-Block wurde nicht gefunden").toBeGreaterThan(0)
        const dunkelBlock = CSS.slice(start, CSS.indexOf("}", start))
        for (const name of ["bg", "stripe", "border"]) {
            expect(dunkelBlock, `--planner-pruefung-${name} fehlt im Dunkelmodus`)
                .toContain(`--planner-pruefung-${name}:`)
        }
    })
})
