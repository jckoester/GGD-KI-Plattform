/**
 * Persönlicher Ausfall in der Oberfläche (Paket 5, AP4).
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import {
    darfZurueckgenommenWerden,
    eintragFrage,
    herkunftText,
    ruecknahmeWarnung,
} from "./ausfall.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const ZEILE = readFileSync(join(SRC, "lib/components/planner/PlannerRow.svelte"), "utf8")

describe("herkunftText", () => {
    it("unterscheidet die drei Quellen", () => {
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "stundenplan" }))
            .toContain("Stundenplan")
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "eigen" }))
            .toContain("selbst")
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "assistent" }))
            .toContain("Assistenten")
    })

    it("⚠️ prüft die Kategorie mit", () => {
        // `ausfall_herkunft` bleibt stehen, wenn eine Stunde die Kategorie über einen
        // Weg verlässt, der die Felder nicht mitführt — der Snapshot-Restore schreibt
        // aus einem JSON ohne diese Spalten. Ohne die Prüfung meldete die Zeile einen
        // Ausfall, den es nicht mehr gibt.
        expect(herkunftText({ kategorie: "unterricht", ausfall_herkunft: "eigen" }))
            .toBeNull()
    })

    it("schweigt bei unbekannter Herkunft", () => {
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: null })).toBeNull()
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "irgendwas" }))
            .toBeNull()
    })
})

describe("darfZurueckgenommenWerden", () => {
    it("nur Eigenes", () => {
        expect(darfZurueckgenommenWerden(
            { kategorie: "ausfall", ausfall_herkunft: "eigen" })).toBe(true)
        // Ein Ausfall aus dem Stundenplan gehört dem Abgleich — ihn hier zu entfernen
        // überschriebe eine Auskunft der Schule, die ohnehin wiederkäme.
        expect(darfZurueckgenommenWerden(
            { kategorie: "ausfall", ausfall_herkunft: "stundenplan" })).toBe(false)
    })
})

describe("ruecknahmeWarnung", () => {
    it("⚠️ kündigt an, was sonst still geschähe", () => {
        // F4: Nach dem Schreiben ist einzeln von tagesweit nicht mehr unterscheidbar.
        const w = ruecknahmeWarnung("tag")
        expect(w).toContain("einzeln")
        expect(w).toContain("Stundenplan")
    })

    it("schweigt, wo es nichts anzukündigen gibt", () => {
        expect(ruecknahmeWarnung("gruppe")).toBeNull()
    })
})

describe("eintragFrage", () => {
    it("nennt die Reichweite beim Namen", () => {
        expect(eintragFrage("tag")).toContain("Alle Ihre Stunden dieses Tages")
        expect(eintragFrage("gruppe", "9C")).toContain("9C")
    })
})

describe("Zeile im Jahresplan (Quelltext-Wächter)", () => {
    it("zeigt die Herkunft an", () => {
        // Ohne sie sähen ein Stundenplan-Ausfall und ein selbst gesetzter gleich aus,
        // und die Lehrkraft wüsste nicht, ob sie ihn zurücknehmen kann.
        expect(ZEILE).toMatch(/\{#if herkunft\}/)
    })

    it("bietet beide Wege an, aber nie beide zugleich", () => {
        expect(ZEILE).toMatch(/\{#if eigenerAusfall\}/)
        expect(ZEILE).toContain("Ausfall zurücknehmen")
        expect(ZEILE).toContain("Ich falle aus")
    })
})

describe("Planungsseite: Auffrischen nach einer Server-Aktion", () => {
    const SEITE = readFileSync(
        join(SRC, "routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte"),
        "utf8",
    )

    it("⚠️ übernimmt die Slots des Servers, statt die lokalen zu behalten", () => {
        // Gemeldet von Jan (24.09.2026): Ein ganztägiger Ausfall erschien erst nach
        // manuellem Neuladen. Die Auffrischung behielt für bestehende Slots die lokale
        // Kopie — richtig auf dem PATCH-Pfad, falsch nach allem, was der Server von
        // sich aus ändert. Derselbe Fehler bestand beim Löschen einer Einheit
        // (`ON DELETE SET NULL` auf `ue_node_id`).
        const fn = SEITE.slice(SEITE.indexOf("async function refreshVomServer"))
        const rumpf = fn.slice(0, fn.indexOf("\n  }"))
        expect(rumpf).toContain("slots = refreshed.slots")
        expect(rumpf).not.toMatch(/slots\.find\(/)
    })

    it("beide Ausfall-Wege frischen auf", () => {
        // Ohne das bliebe die Zeile stehen, wie sie war — und die Lehrkraft hielte den
        // Eintrag für gescheitert.
        for (const fn of ["ausfallGanzerTag", "ausfallZurueck"]) {
            const block = SEITE.slice(SEITE.indexOf(`async function ${fn}`))
            expect(block.slice(0, block.indexOf("\n  }")), fn)
                .toContain("refreshVomServer()")
        }
    })
})
