/**
 * Das Inhaltsverzeichnis der Hilfe gegen `docs/user/` (Paket 8, AP1).
 *
 * ⚠️ **Der Fehler, den dieser Wächter verhindert, war acht Seiten groß.** Bis zum
 * 26.09.2026 kostete jede Hilfeseite ein eigenes Verzeichnis mit einer `+page.svelte`,
 * die immer dasselbe tat. Acht von achtzehn Dokumenten hatten keins und waren in der
 * Anwendung unerreichbar — darunter `stundenplan.md`, vier Tage zuvor deutlich
 * erweitert. Wer Doku schreibt, schreibt sie in `docs/user/` und merkt nicht, dass sie
 * nicht ankommt.
 *
 * Geprüft wird in **beide** Richtungen: keine Datei ohne Eintrag, kein Eintrag ohne
 * Datei. Die zweite Richtung ist die unauffälligere — ein Eintrag, dessen Datei fehlt,
 * führt auf eine leere Seite.
 */
import { describe, it, expect } from "vitest"
import { readdirSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { helpNav, helpEintrag, sichtbareHilfe } from "./help-nav.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const DOCS = join(SRC, "../../docs/user")

const dateien = () =>
    readdirSync(DOCS)
        .filter((n) => n.endsWith(".md"))
        .map((n) => n.replace(/\.md$/, ""))

describe("Inhaltsverzeichnis und Dokumente", () => {
    it("⚠️ jede Datei in docs/user/ ist erreichbar", () => {
        const verzeichnet = new Set(helpNav.map((e) => e.file))
        const fehlend = dateien().filter((d) => !verzeichnet.has(d))
        expect(fehlend, "Dokument(e) ohne Eintrag in `helpNav`").toEqual([])
    })

    it("⚠️ jeder Eintrag zeigt auf eine Datei, die es gibt", () => {
        const vorhanden = new Set(dateien())
        const tot = helpNav.filter((e) => !vorhanden.has(e.file)).map((e) => e.file)
        expect(tot, "Eintrag/Einträge ohne Datei — die Seite bliebe leer").toEqual([])
    })

    it("die Pfade sind eindeutig und die Übersicht liegt auf /help", () => {
        const pfade = helpNav.map((e) => e.path)
        expect(new Set(pfade).size).toBe(pfade.length)
        expect(helpEintrag("")?.path).toBe("/help")
        expect(helpEintrag("chat")?.path).toBe("/help/chat")
    })

    it("unbekannte Pfadstücke ergeben keinen Eintrag — die Route antwortet mit 404", () => {
        expect(helpEintrag("gibt-es-nicht")).toBeNull()
    })
})

describe("Wer welchen Eintrag sieht", () => {
    const slugs = (rollen) => sichtbareHilfe(rollen).map((e) => e.slug)

    it("Schüler:innen sehen die Lehrkraft-Seiten nicht im Verzeichnis", () => {
        const sicht = slugs(["student"])
        for (const nur_lehrkraft of ["unterrichtsplanung", "curriculum", "stundenplan"]) {
            expect(sicht).not.toContain(nur_lehrkraft)
        }
        expect(sicht).toContain("schueler")
        expect(sicht).toContain("chat")
    })

    it("Lehrkräfte sehen sie, aber nicht die Admin-Seite", () => {
        const sicht = slugs(["teacher"])
        expect(sicht).toContain("unterrichtsplanung")
        expect(sicht).toContain("erste-30-minuten")
        expect(sicht).not.toContain("guardrails")
    })

    it("Admins sehen alles", () => {
        expect(slugs(["teacher", "admin"]).length).toBe(helpNav.length)
    })

    it("⚠️ gefiltert heißt nicht gesperrt", () => {
        // Die Seiten sind nicht geheim, nur unpassend (Entscheidung Jan, 26.09.2026).
        // Gesperrt ist genau eine — und das steht ausdrücklich an ihr.
        const geschuetzt = helpNav.filter((e) => e.geschuetzt).map((e) => e.slug)
        expect(geschuetzt).toEqual(["guardrails"])
    })
})

describe("Die Route bedient alle Einträge", () => {
    const ROUTE = readFileSync(
        join(SRC, "routes/(app)/help/[seite]/+page.js"),
        "utf8",
    )

    it("prüft das Pfadstück gegen das Verzeichnis", () => {
        expect(ROUTE).toContain("helpEintrag(params.seite)")
        expect(ROUTE).toContain("error(404")
    })

    it("hält die Admin-Prüfung der Guardrail-Seite aufrecht", () => {
        // Sie stand vor dem Umbau unter dieser Prüfung; ein Umbau darf sie nicht
        // nebenbei aufheben.
        expect(ROUTE).toContain("geschuetzt")
        expect(ROUTE).toContain('includes(\'admin\')')
    })
})
