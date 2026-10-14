/**
 * Admin-Seite „Fachbegriffe" (0.15.2): Einspielen in jedes Fach, auch ohne Fachschaft.
 *
 * Derselbe Dialog wie auf der Fachseite, aber mit dem Fach **aus der Datei**: Ein Lauf
 * darf mehrere Fächer enthalten, das gewählte Fach ist nur die Vorgabe für Dateien ohne
 * `fach:` und wählt, was Liste und „Als Zip" zeigen.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const lies = (pfad) => readFileSync(join(SRC, pfad), "utf8")

describe("Admin-Seite Fachbegriffe", () => {
    const SEITE = lies("routes/(admin)/settings/fachbegriffe/+page.svelte")

    it("ist nur für Admins", () => {
        const LADEN = lies("routes/(admin)/settings/fachbegriffe/+page.js")
        expect(LADEN).toMatch(/if \(!\$user\?\.roles\.includes\("admin"\)\) \{\s*redirect\(302, "\/"\);/)
    })

    it("bietet alle Fächer zur Wahl", () => {
        expect(SEITE).toMatch(/\{#each \$subjects as s \(s\.slug\)\}/)
    })

    it("importiert mit dem Fach aus der Datei, das gewählte Fach nur als Vorgabe", () => {
        expect(SEITE).toMatch(
            /<FachbegriffImportDialog\s+ausDatei=\{true\}\s+fach=\{fach\?\.slug \?\? null\}/,
        )
    })

    it("die Liste zeigt das gewählte Fach — ohne eigenen, gebundenen Import", () => {
        // Sonst stünden zwei „Aus Dateien" auf der Seite, einer gebunden, einer nicht.
        expect(SEITE).toMatch(/<KnowledgeNodeList[\s\S]*fixedSubjectSlug=\{fach\.slug\}/)
        expect(SEITE).not.toMatch(/importFach=/)
    })

    it("lädt die Liste nach einem Import neu", () => {
        expect(SEITE).toMatch(/\{#key `\$\{fach\.slug\}-\$\{stand\}`\}/)
        expect(SEITE).toMatch(/onfertig=\{\(\) => \(stand \+= 1\)\}/)
    })
})

describe("Wege dorthin", () => {
    it("Kachel in den Einstellungen", () => {
        expect(lies("routes/(admin)/settings/+page.svelte")).toMatch(/href="\/settings\/fachbegriffe"/)
    })

    it("Eintrag in der Admin-Seitenleiste", () => {
        expect(lies("lib/components/AdminSidebar.svelte")).toMatch(/goto\('\/settings\/fachbegriffe'\)/)
    })
})

describe("Import-Dialog mit Fach aus der Datei", () => {
    const DIALOG = lies("lib/components/FachbegriffImportDialog.svelte")

    it("reicht den Schalter an die API weiter", () => {
        expect(DIALOG).toMatch(/importiereFachbegriffe\(fach, dateien, \{\s*probelauf,\s*ueberschreiben,\s*ausDatei,\s*\}\)/)
    })

    it("nennt je Zeile das Fach, wohin die Datei geht", () => {
        expect(DIALOG).toMatch(/\{#if ausDatei && zeile\.fach\}[\s\S]{0,200}→ \{zeile\.fach\}/)
    })
})
