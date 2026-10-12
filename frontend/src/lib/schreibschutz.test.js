/**
 * Schreibgeschütztes `config/` (0.15.1): Budget- und Ferienseite sagen es selbst und
 * sperren das Speichern — statt erst beim Klick mit einem 500 zu scheitern.
 *
 * Das Backend liefert dafür `schreibschutz` (Text oder `null`) in seiner Antwort.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const lies = (pfad) => readFileSync(join(SRC, pfad), "utf8")

describe("Budget-Seite", () => {
    const SEITE = lies("routes/(admin)/budget/+page.svelte")

    it("zeigt den Schreibschutz als Warnung", () => {
        expect(SEITE).toMatch(/\{#if data\.schreibschutz\}\s*<div[^>]*><WarningBanner message=\{data\.schreibschutz\}/)
    })

    it("sperrt Speichern bei Schreibschutz", () => {
        expect(SEITE).toMatch(/disabled=\{[^}]*!!data\.schreibschutz\}\s*onclick=\{\(\) => showConfirm = true\}/)
    })
})

describe("Ferienkalender", () => {
    const SEITE = lies("routes/(admin)/settings/holidays/+page.svelte")

    it("zeigt den Schreibschutz und verweist aufs Kopieren", () => {
        expect(SEITE).toMatch(/\{#if vorschlag\.schreibschutz\}[\s\S]{0,200}<WarningBanner[\s\S]{0,120}kopieren/)
    })

    it("sperrt Übernehmen bei Schreibschutz", () => {
        expect(SEITE).toMatch(/onclick=\{uebernehmen\}\s*disabled=\{[^}]*!!vorschlag\.schreibschutz\}/)
    })
})
