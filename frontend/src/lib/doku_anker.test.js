/**
 * Seitenanker in der Anwenderdokumentation.
 *
 * ⚠️ **Der Anlass** (24.09.2026, bei AP8 von Paket 5): Die Doku trug acht `](#…)`-Links,
 * von denen **keiner** funktionierte. `marked` erzeugt von sich aus keine `id` an
 * Überschriften, und `renderer.link` hängte `target="_blank"` an *jeden* Link — ein
 * Seitenanker öffnete also eine neue Seite, und zwar ohne Sprungziel.
 *
 * Sechs der acht Links waren älter als dieser Tag. Niemand hatte es bemerkt: Ein toter
 * Anker sieht aus wie ein Weg und sagt nichts, wenn man ihn geht.
 */
import { describe, it, expect } from "vitest"
import { readdirSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { ueberschriftId } from "./markdown.js"

// src/lib → src → frontend → Repo-Wurzel: vier Ebenen, nicht drei.
const WURZEL = dirname(dirname(dirname(dirname(fileURLToPath(import.meta.url)))))
const DOKU = join(WURZEL, "docs/user")

function dateien() {
    return readdirSync(DOKU).filter((f) => f.endsWith(".md"))
}

describe("ueberschriftId", () => {
    it("bildet die Kennung wie die vorhandenen Anker", () => {
        expect(ueberschriftId("Was Schüler:innen mitbekommen"))
            .toBe("was-schülerinnen-mitbekommen")
        expect(ueberschriftId("Das ganze Jahr planen")).toBe("das-ganze-jahr-planen")
        expect(ueberschriftId("Aus einem Chat-Ergebnis einen Baustein machen"))
            .toBe("aus-einem-chat-ergebnis-einen-baustein-machen")
    })

    it("behält Umlaute", () => {
        // Sie stehen in den vorhandenen Ankern; sie zu ersetzen bräche sie alle.
        expect(ueberschriftId("Prüfung & Ausfall")).toBe("prüfung-ausfall")
    })
})

describe("⚠️ Jeder Seitenanker in der Anwenderdoku hat ein Ziel", () => {
    for (const datei of dateien()) {
        const text = readFileSync(join(DOKU, datei), "utf8")
        const anker = [...text.matchAll(/\]\(#([^)]+)\)/g)].map((m) => m[1])
        if (!anker.length) continue

        it(`${datei}: ${anker.length} Anker`, () => {
            const ziele = new Set(
                [...text.matchAll(/^#{1,6}\s+(.+)$/gm)].map((m) => ueberschriftId(m[1])),
            )
            const tot = anker.filter((a) => !ziele.has(a))
            expect(tot, `tote Anker in ${datei}: ${tot}`).toEqual([])
        })
    }
})
