import { describe, it, expect } from "vitest"
import {
    angebotsHinweis,
    hatKandidaten,
    kandidatZeile,
    zuordnenErgebnis,
    zuordnenFrage,
} from "./gruppenangebote.js"

describe("kandidatZeile", () => {
    it("nennt den Beleg, an dem die Gruppe wiedererkannt wird", () => {
        // ⚠️ Ohne Beleg wählt die Lehrkraft zwischen gleich aussehenden Namen — und
        // eine falsche Wahl verschmilzt zwei Jahrespläne.
        const zeile = kandidatZeile({ name: "Chemie 9D", fach: "Chemie", beleg: "12 Stunden · 4 Chats" })
        expect(zeile).toContain("12 Stunden")
        expect(zeile).toContain("4 Chats")
    })

    it("wiederholt das Fach nicht, wenn es schon im Namen steht", () => {
        const zeile = kandidatZeile({ name: "Chemie 9D", fach: "Chemie", beleg: "noch ohne Planung" })
        expect(zeile.match(/Chemie/g)).toHaveLength(1)
    })
})

describe("zuordnenFrage", () => {
    const frage = zuordnenFrage({ name: "unterricht.9d.ch" }, { name: "Chemie 9D" })

    it("nennt beide Seiten", () => {
        expect(frage).toContain("unterricht.9d.ch")
        expect(frage).toContain("Chemie 9D")
    })

    it("nennt die Folge für die Mitglieder", () => {
        // Ohne diesen Satz führt die Lehrkraft blind zusammen.
        expect(frage).toContain("Schulkonto")
        expect(frage).toContain("verliert die Mitgliedschaft")
    })

    it("sagt, was bleibt", () => {
        expect(frage).toContain("Jahresplan")
    })
})

describe("zuordnenErgebnis", () => {
    it("schweigt über Entfernungen, wenn es keine gab", () => {
        expect(zuordnenErgebnis({ geerbte_entfernt: 0 })).not.toContain("entfernt")
    })

    it("nennt die Zahl, wenn geerbte Mitgliedschaften fielen", () => {
        const satz = zuordnenErgebnis({ geerbte_entfernt: 24 })
        expect(satz).toContain("24")
        expect(satz).toContain("entfernt")
    })

    it("formuliert die Einzahl richtig", () => {
        expect(zuordnenErgebnis({ geerbte_entfernt: 1 })).toContain("Mitgliedschaft wurde")
    })
})

describe("angebotsHinweis", () => {
    it("erklärt, warum nichts von selbst entsteht", () => {
        const satz = angebotsHinweis({ angebote: [{ ignoriert: false }] })
        expect(satz).toContain("Angelegt wird nichts von selbst")
    })

    it("zählt ignorierte nicht mit", () => {
        expect(angebotsHinweis({ angebote: [{ ignoriert: true }] })).toBeNull()
    })

    it("schweigt ohne Angebote", () => {
        expect(angebotsHinweis({ angebote: [] })).toBeNull()
        expect(angebotsHinweis(null)).toBeNull()
    })
})

describe("hatKandidaten", () => {
    it("erkennt, wenn es nichts zuzuordnen gibt", () => {
        expect(hatKandidaten({ gruppen: [] })).toBe(false)
        expect(hatKandidaten({ gruppen: [{ id: 1 }] })).toBe(true)
    })
})
