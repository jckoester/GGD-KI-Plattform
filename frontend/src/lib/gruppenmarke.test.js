/**
 * Die Unterrichtsgruppe eines Chats in Liste und Sidebar (Paket 7, AP5).
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { chatTooltip, gruppenMarke, gruppeZumChat } from "./gruppenmarke.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))

const GRUPPEN = [
    { id: 1, name: "M 10C", type: "teaching_group" },
    { id: 2, name: "Naturwissenschaft und Technik 10A/10B/10C", type: "teaching_group" },
]

describe("gruppeZumChat", () => {
    it("findet die Gruppe zur Konversation", () => {
        expect(gruppeZumChat(1, GRUPPEN)?.name).toBe("M 10C")
    })

    it("⚠️ schweigt in allen drei Leerfällen", () => {
        // Kein Gruppenbezug, Gruppe unbekannt (nach dem Austritt), Liste noch nicht
        // geladen. Für die Anzeige ist das dasselbe: nichts zeigen. Eine Marke zu
        // erfinden wäre in jedem der drei falsch.
        expect(gruppeZumChat(null, GRUPPEN)).toBeNull()
        expect(gruppeZumChat(99, GRUPPEN)).toBeNull()
        expect(gruppeZumChat(1, [])).toBeNull()
        expect(gruppeZumChat(1, undefined)).toBeNull()
    })
})

describe("gruppenMarke", () => {
    const alsLehrkraft = { istLehrkraft: true }

    it("nimmt den Namen, wie ihn das Backend auflöst", () => {
        // `GroupOut.name` ist bereits `display_name or name` — die Kurzform entsteht
        // dort, wo die Lehrkraft sie vergibt, nicht hier.
        expect(gruppenMarke(1, GRUPPEN, alsLehrkraft)).toBe("M 10C")
    })

    it("⚠️ kürzt lange Namen **nicht**", () => {
        // Naheliegend wäre „N 10A/10B/10C". Eine Abkürzung, die niemand gewählt hat,
        // stünde dann in jeder Zeile — und bei Mathematik sähe sie gut aus, hier nicht.
        // Gekürzt wird in der Darstellung (CSS), nicht in den Daten.
        expect(gruppenMarke(2, GRUPPEN, alsLehrkraft)).toBe(
            "Naturwissenschaft und Technik 10A/10B/10C",
        )
    })

    it("⚠️ schweigt gegenüber Schüler:innen", () => {
        // Aus Schülersicht *ist* die Unterrichtsgruppe das Fach (CLAUDE.md): Sie sehen
        // „Mathematik", nicht „M 10C". Die Vorgabe ist deshalb `false` — wer die Marke
        // will, sagt es ausdrücklich.
        expect(gruppenMarke(1, GRUPPEN)).toBeNull()
        expect(gruppenMarke(1, GRUPPEN, { istLehrkraft: false })).toBeNull()
    })

    it("schweigt ohne Gruppe", () => {
        expect(gruppenMarke(null, GRUPPEN, alsLehrkraft)).toBeNull()
        expect(gruppenMarke(99, GRUPPEN, alsLehrkraft)).toBeNull()
    })

    it("schweigt bei leerem Namen statt einen leeren Kasten zu zeigen", () => {
        expect(gruppenMarke(3, [{ id: 3, name: "   " }], alsLehrkraft)).toBeNull()
    })
})

describe("chatTooltip", () => {
    it("nennt Titel und Gruppe", () => {
        expect(chatTooltip("Sinusfunktionen", "M 10C")).toBe("Sinusfunktionen · M 10C")
    })

    it("⚠️ stellt den Titel voran", () => {
        // In der Sidebar ist der Titel abgeschnitten; wer den Zeiger daraufhält, will
        // zuerst wissen, wie der Chat vollständig heißt.
        expect(chatTooltip("Ein sehr langer Titel", "M 10C")).toMatch(/^Ein sehr langer/)
    })

    it("kommt ohne Gruppe und ohne Titel aus", () => {
        expect(chatTooltip("Sinusfunktionen", null)).toBe("Sinusfunktionen")
        expect(chatTooltip(null, "M 10C")).toBe("Unbenannter Chat · M 10C")
        expect(chatTooltip("   ", null)).toBe("Unbenannter Chat")
    })
})

describe("Beide Listen benutzen dieselbe Regel", () => {
    const HISTORY = readFileSync(
        join(SRC, "routes/(app)/history/+page.svelte"),
        "utf8",
    )
    const SIDEBAR = readFileSync(join(SRC, "lib/components/Sidebar.svelte"), "utf8")

    it("⚠️ keine zweite Fassung im Markup", () => {
        // Zwei Listen, dieselbe Frage. Würde eine von ihnen den Namen selbst
        // zusammensetzen, liefen sie irgendwann auseinander — und niemand sähe es,
        // weil beide für sich plausibel aussehen.
        for (const [name, quelle] of [["History", HISTORY], ["Sidebar", SIDEBAR]]) {
            expect(quelle, name).toContain("gruppenmarke.js")
        }
    })

    it("die Sidebar zeigt die Gruppe im Tooltip, nicht als eigene Zeile", () => {
        // Dort ist der Platz knapp: Titel, Datum und Menü teilen sich eine Zeile.
        expect(SIDEBAR).toContain("chatTooltip(")
    })

    it("die History zeigt sie sichtbar — dort ist Platz", () => {
        expect(HISTORY).toContain("gruppenMarke(")
    })
})
