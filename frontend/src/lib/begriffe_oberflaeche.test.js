/**
 * Wächter: Wörter, die die Oberfläche nicht mehr benutzt (0.40, Päckchen AM).
 *
 * „Knoten“ ist das Wort der Datenstruktur; in der Oberfläche heißt dasselbe „Baustein“
 * (Schritt 7a). Durchsucht werden alle `.svelte`- und `.js`-Dateien unter `src/` außer Tests —
 * **ohne** Kommentare und ohne Log-Ausgaben (`console.*`), die nur Entwickler:innen lesen.
 * Bezeichner (`zumKnoten`, `KnotenTyp`) zählen nicht: Davor oder dahinter steht ein Buchstabe.
 *
 * Dazu die alten Namen aus 0.40 (Schritt 8): „Wissensgraph“ und „Kontextspeicher“ heißen
 * „Bibliothek“, „Artefakt“ heißt „Produkt“, die Knöpfe „In Bibliothek (speichern)“ und die
 * „Material-Werkstatt“ heißen „Werkstatt“. Ausgenommen sind Sätze, die den Umzug erklären
 * („hieß bisher …“). Dieselben Wörter prüft der Test auch in `docs/user` — die Hilfe wird in
 * der Oberfläche angezeigt (Plan 0.40, Gegenprüfung 13).
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

const HILFE = join(SRC, "..", "..", "docs", "user")

/** Sätze, die den Umzug erklären, dürfen die alten Namen nennen. */
const ERKLAERT_UMZUG = /hieß bisher|bisher hieß|früher .*hieß|bis 0\.40/

function fundstellen(muster, { quellen = dateien(SRC), wurzel = SRC, aufbereiten = lesbar } = {}) {
    const treffer = []
    for (const pfad of quellen) {
        aufbereiten(readFileSync(pfad, "utf8")).split("\n").forEach((zeile) => {
            if (muster.test(zeile) && !ERKLAERT_UMZUG.test(zeile)) {
                treffer.push(`${relative(wurzel, pfad)}: ${zeile.trim()}`)
            }
        })
    }
    return treffer
}

const hilfeseiten = () =>
    readdirSync(HILFE).filter((n) => n.endsWith(".md")).map((n) => join(HILFE, n))

/** Alte Namen aus 0.40 — außerhalb von Bezeichnern (davor/dahinter kein Buchstabe). */
const ALTE_NAMEN = /(?<![A-Za-zäöüß])(Wissensgraph|Kontextspeicher|Artefakt|Material-Werkstatt|In Bibliothek)/

describe("Wörter, die die Oberfläche nicht mehr benutzt", () => {
    it("„Knoten“ heißt „Baustein“", () => {
        expect(fundstellen(/(?<![A-Za-zäöüß])Knoten(?![A-Z_])/)).toEqual([])
    })

    it("„Wissensgraph“, „Kontextspeicher“, „Artefakt“ und die alten Knöpfe sind umbenannt", () => {
        expect(fundstellen(ALTE_NAMEN)).toEqual([])
    })

    it("auch nicht in der Hilfe", () => {
        expect(fundstellen(ALTE_NAMEN, { quellen: hilfeseiten(), wurzel: HILFE, aufbereiten: (t) => t })).toEqual([])
        expect(
            fundstellen(/(?<![A-Za-zäöüß])Knoten(?![A-Za-z_])/, { quellen: hilfeseiten(), wurzel: HILFE, aufbereiten: (t) => t }),
        ).toEqual([])
    })

    it("die Suche greift überhaupt", () => {
        // Gegenprobe: Ein kaputtes Muster bliebe für immer grün.
        expect(fundstellen(/(?<![A-Za-zäöüß])Baustein/).length).toBeGreaterThan(20)
    })
})
