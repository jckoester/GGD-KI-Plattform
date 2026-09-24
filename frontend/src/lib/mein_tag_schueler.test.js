/**
 * Die Schüler:innen-Sicht der Startseite (AP5).
 *
 * Getrennt von `mein_tag.test.js`, weil die Trennung der Rollen hier der Gegenstand ist:
 * Was die Lehrkraft sieht und was Schüler:innen sehen, sind zwei Antworten, nicht eine
 * mit Weichen.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { fachLink, schuelerLeerSatz, zeigtSchuelerTag } from "./mein_tag.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const KACHEL = readFileSync(join(SRC, "lib/components/SchuelerTagKachel.svelte"), "utf8")

describe("fachLink", () => {
    it("führt auf die Fachseite, nicht in die Gruppenplanung", () => {
        // Dort liegen Assistenten und eigene Chats. Die Planungsansicht der Gruppe
        // gehört der Lehrkraft.
        expect(fachLink({ subject_slug: "mathematik" })).toBe("/subjects/mathematik")
        expect(fachLink({ subject_slug: "mathematik" })).not.toContain("planner")
    })

    it("baut ohne Fach-Slug keinen Link", () => {
        expect(fachLink({ group_id: 7 })).toBeNull()
        expect(fachLink(null)).toBeNull()
    })
})

describe("schuelerLeerSatz", () => {
    it("⚠️ fordert nicht zum Einrichten auf", () => {
        // `leerSatz` (Lehrkraft) sagt „Legen Sie eine an". Eine Schüler:in kann keine
        // Unterrichtsgruppe anlegen — der Satz wäre eine Sackgasse.
        const satz = schuelerLeerSatz({ grund: "kein_unterricht" }, false)
        expect(satz).not.toMatch(/legen sie|anlegen|einrichten Sie/i)
        expect(satz).toContain("eingerichtet")
    })

    it("erklärt den unterrichtsfreien Tag", () => {
        expect(schuelerLeerSatz({ grund: "ferien" }, true)).toBe("Ferien.")
        expect(schuelerLeerSatz({ grund: "wochenende" }, true)).toBe("Wochenende.")
        expect(schuelerLeerSatz({ grund: "kein_unterricht" }, true))
            .toBe("Für diesen Tag ist hier nichts eingetragen.")
    })
})

describe("Schüler:innen-Kachel (Quelltext-Wächter)", () => {
    it("⚠️ zeigt kein Thema, keine Einheit, keinen Entwurf", () => {
        // Die Felder stehen schon in der Antwort nicht drin (Integrationstest
        // `test_mein_tag_schueler_traegt_keine_planungsfelder`). Dieser Wächter fängt
        // den Fall ab, dass jemand sie später doch heranzieht — etwa beim Vereinheitlichen
        // der beiden Kacheln.
        for (const feld of ["thema", "ue_titel", "ue_node_id", "stunde_node_id",
                            "hat_entwurf", "kategorie"]) {
            expect(KACHEL, `Planungsfeld im Markup: ${feld}`).not.toContain(feld)
        }
    })

    it("verlinkt das Fach", () => {
        expect(KACHEL).toMatch(/<a href=\{ziel\}/)
    })
})

describe("zeigtSchuelerTag", () => {
    it("⚠️ verschweigt den Schultag ohne Einträge", () => {
        expect(zeigtSchuelerTag({ faecher: [], grund: "kein_unterricht" }, true)).toBe(false)
    })

    it("zeigt den Tag mit Fächern und die Gründe aus dem Kalender", () => {
        expect(zeigtSchuelerTag({ faecher: [{}] }, true)).toBe(true)
        expect(zeigtSchuelerTag({ faecher: [], grund: "ferien" }, true)).toBe(true)
    })

    it("erklärt, wenn noch gar keine Fächer da sind", () => {
        // Eine Schüler:in kann nichts einrichten — aber eine völlig leere Seite ohne
        // Erklärung wäre schlechter als der eine Satz.
        expect(zeigtSchuelerTag({ faecher: [], grund: "kein_unterricht" }, false)).toBe(true)
    })
})
