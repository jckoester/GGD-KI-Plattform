/**
 * Wächter: Wörter, die die Oberfläche nicht mehr benutzt (0.40, Päckchen AM).
 *
 * „Knoten“ ist das Wort der Datenstruktur; in der Oberfläche heißt dasselbe „Baustein“
 * (Schritt 7a). Durchsucht werden alle `.svelte`- und `.js`-Dateien unter `src/` außer Tests —
 * **ohne** Kommentare und ohne Log-Ausgaben (`console.*`), die nur Entwickler:innen lesen.
 * Bezeichner (`zumKnoten`, `KnotenTyp`) zählen nicht: Davor oder dahinter steht ein Buchstabe.
 *
 * Schritt 8 ergänzt hier „Wissensgraph“ und „Artefakt“.
 */
import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative } from "node:path"

const SRC = join(import.meta.dirname, "..")

function dateien(verzeichnis) {
    return readdirSync(verzeichnis).flatMap((name) => {
        const pfad = join(verzeichnis, name)
        if (statSync(pfad).isDirectory()) return dateien(pfad)
        return /\.(svelte|js)$/.test(name) && !/\.test\.js$/.test(name) ? [pfad] : []
    })
}

/** Quelltext ohne Kommentare und Log-Zeilen — was übrig bleibt, kann jemand lesen. */
function lesbar(quelle) {
    return quelle
        .replace(/<!--[\s\S]*?-->/g, "")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/(^|[^:"'`])\/\/[^\n]*/g, "$1")
        .replace(/console\.\w+\([\s\S]*?\);?/g, "")
}

function fundstellen(muster) {
    const treffer = []
    for (const pfad of dateien(SRC)) {
        lesbar(readFileSync(pfad, "utf8")).split("\n").forEach((zeile) => {
            if (muster.test(zeile)) treffer.push(`${relative(SRC, pfad)}: ${zeile.trim()}`)
        })
    }
    return treffer
}

describe("Wörter, die die Oberfläche nicht mehr benutzt", () => {
    it("„Knoten“ heißt „Baustein“", () => {
        expect(fundstellen(/(?<![A-Za-zäöüß])Knoten(?![A-Z_])/)).toEqual([])
    })

    it("die Suche greift überhaupt", () => {
        // Gegenprobe: Ein kaputtes Muster bliebe für immer grün.
        expect(fundstellen(/(?<![A-Za-zäöüß])Baustein/).length).toBeGreaterThan(20)
    })
})
