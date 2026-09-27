/**
 * Wächter für die Startseite: die Kachelaufstellung und das Layout, das daran hängt.
 *
 * ⚠️ **Was hier geprüft wird, ist eine Invariante, keine Optik.** Ob die Seite „schön"
 * mittig steht, kann kein Test sagen. Wohl aber, ob die beiden Dinge zusammenhängen, die
 * zusammenhängen müssen: Was gerendert wird, und woran die Zentrierung hängt. Laufen sie
 * auseinander, zentriert sich die Seite mit Inhalt darunter — und schneidet ihn oben ab.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const SEITE = readFileSync(join(SRC, "routes/(app)/welcome/+page.svelte"), "utf8")

/** Die Schlüssel aus `const kacheln = $derived({ … })`. */
function aufstellung() {
    const block = SEITE.slice(SEITE.indexOf("const kacheln = $derived({"))
    const ende = block.indexOf("})")
    return new Set([...block.slice(0, ende).matchAll(/^\s{8}(\w+):/gm)].map((m) => m[1]))
}

/**
 * Die im Markup benutzten `kacheln.X`.
 *
 * Die Vorschau (`(?<!\w)`) ist nötig: Ohne sie fängt das Muster auch den Import von
 * `startkacheln.js` mit und meldet einen Schlüssel `js`, den es nie gab.
 */
function benutzt() {
    return new Set([...SEITE.matchAll(/(?<!\w)kacheln\.(\w+)/g)].map((m) => m[1]))
}

describe("Startseite: Kacheln und Zentrierung", () => {
    it("zentriert genau dann, wenn keine Kachel steht", () => {
        expect(SEITE).toMatch(/class:justify-center=\{!hatKacheln\}/)
        expect(SEITE).toMatch(/const hatKacheln = \$derived\(Object\.values\(kacheln\)\.some\(Boolean\)\)/)
    })

    it("⚠️ jede Kachel im Markup steht auch in der Aufstellung", () => {
        // Sonst ist die Bedingung `undefined` — die Kachel erschiene nie, lautlos.
        const fehlend = [...benutzt()].filter((k) => !aufstellung().has(k))
        expect(fehlend, `nicht in der Aufstellung: ${fehlend}`).toEqual([])
    })

    it("⚠️ jeder Eintrag der Aufstellung wird auch gerendert", () => {
        // Sonst zählt eine Kachel für die Zentrierung mit, die es gar nicht gibt — die
        // Seite bliebe oben stehen, obwohl nichts darunter steht.
        const ungenutzt = [...aufstellung()].filter((k) => !benutzt().has(k))
        expect(ungenutzt, `nie gerendert: ${ungenutzt}`).toEqual([])
    })

    it("die Aufstellung ist nicht leer", () => {
        // Ein Regex, der nichts findet, machte beide Prüfungen oben grün und wertlos.
        expect(aufstellung().size).toBeGreaterThan(3)
    })
})
