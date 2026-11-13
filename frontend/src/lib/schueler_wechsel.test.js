/**
 * Schüler-Wechsel (0.41, Päckchen AN, Schritt 9): Was Schüler:innen aus dem Chat behalten,
 * bleibt ein Produkt in der Werkstatt. Kein Komponententest — das Projekt mountet keine
 * Svelte-Komponenten —, sondern die Stellen, an denen die Oberfläche das festmacht.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { RUHENDE_CONTENT_TYPES } from "./taxonomy.js"

const lesen = (...pfad) => readFileSync(join(import.meta.dirname, ...pfad), "utf8")

describe("Schüler-Wechsel", () => {
    it("die drei Schüler-Arten ruhen, strukturierung nicht", () => {
        for (const typ of ["schuelertext", "lernplan", "schuelerpraesentation"]) {
            expect(RUHENDE_CONTENT_TYPES.has(typ)).toBe(true)
        }
        expect(RUHENDE_CONTENT_TYPES.has("strukturierung")).toBe(false)
    })

    it("„Als Baustein speichern“ im Chat nur für Lehrkräfte", () => {
        expect(lesen("components", "MessageBubble.svelte"))
            .toContain("alsBaustein={darfUebernehmen ? alsBausteinSpeichern : null}")
    })

    it("in der Vorschau bietet die Leiste im Chat nichts an, was speichert", () => {
        // Der Server sperrt das Speichern in der Vorschau (`app/auth/vorschau.py`).
        const bubble = lesen("components", "MessageBubble.svelte")
        expect(bubble).toContain("let inVorschau = $derived(!!$user?.vorschau)")
        expect(bubble).toContain("speichern={inVorschau ? null : () => saveImageToLibrary(img.image_id)}")
        expect(bubble).toContain("speichern: inVorschau ? null : () => saveDiagramToLibrary(")
        expect(bubble).toContain("speichern={inVorschau ? null : textSpeichern}")
        expect(bubble).toContain("bearbeiten={inVorschau ? null : openInWorkshop}")
        // Kein weiterer Speichern-Weg an der Vorschau vorbei.
        expect(bubble.match(/speichern[=:] ?\{?\(?\)? ?=?>? ?(saveImageToLibrary|saveDiagramToLibrary|textSpeichern)/g) ?? []).toEqual([])
    })

    it("„Meine Bausteine“ in der Seitenleiste nur für Lehrkräfte", () => {
        const sidebar = lesen("components", "Sidebar.svelte")
        const eintrag = sidebar.indexOf("goto('/knowledge/mine')")
        const davor = sidebar.lastIndexOf("{#if", eintrag)
        expect(sidebar.slice(davor, eintrag)).toContain("{#if istLehrkraft}")
    })

    it("„Meine Bausteine“ verweist Schüler:innen auf die Werkstatt", () => {
        const seite = lesen("..", "routes", "(app)", "knowledge", "mine", "+page.svelte")
        expect(seite).toContain("speicherst du jetzt in deiner Werkstatt")
    })
})
