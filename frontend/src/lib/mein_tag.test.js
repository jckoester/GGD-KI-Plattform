import { describe, it, expect } from "vitest"
import {
    KEIN_NAECHSTER,
    kennzeichen,
    leerFuehrtZurEinrichtung,
    leerSatz,
    naechsterSchritt,
    offeneEntscheidungen,
    plannerLink,
    stundenZeile,
    zweiteUeberschrift,
} from "./mein_tag.js"

const GEPLANT = { hatGruppen: true, hatPlanung: true }

describe("leerSatz", () => {
    it("unterscheidet die drei Lagen", () => {
        // ⚠️ Der Kern der Kachel: „kein Unterricht" ist eine Feststellung, „Ferien" eine
        // Erklärung, „noch nichts geplant" eine Aufforderung.
        const ohneGruppen = leerSatz(null, { hatGruppen: false, hatPlanung: false })
        const ohnePlanung = leerSatz(null, { hatGruppen: true, hatPlanung: false })
        const frei = leerSatz({ grund: "kein_unterricht" }, GEPLANT)
        expect(new Set([ohneGruppen, ohnePlanung, frei]).size).toBe(3)
        expect(ohnePlanung).toContain("Wochenmuster")
    })

    it("benennt Ferien als Ferien", () => {
        // Wer in den Ferien „kein Unterricht" liest, fragt sich, ob etwas fehlt.
        expect(leerSatz({ grund: "ferien" }, GEPLANT)).toBe("Ferien.")
        expect(leerSatz({ grund: "feiertag" }, GEPLANT)).toBe("Feiertag.")
        expect(leerSatz({ grund: "wochenende" }, GEPLANT)).toBe("Wochenende.")
    })

    it("fällt auf eine Feststellung zurück, wenn der Grund fehlt", () => {
        expect(leerSatz({}, GEPLANT)).toBe("Kein Unterricht.")
    })
})

describe("leerFuehrtZurEinrichtung", () => {
    it("führt nur dort hin, wo es etwas einzurichten gibt", () => {
        expect(leerFuehrtZurEinrichtung({ hatGruppen: false })).toBe(true)
        expect(leerFuehrtZurEinrichtung({ hatGruppen: true, hatPlanung: false })).toBe(true)
        expect(leerFuehrtZurEinrichtung(GEPLANT)).toBe(false)
    })
})

describe("zweiteUeberschrift", () => {
    it("heißt nie Morgen", () => {
        // Am Freitag wäre „Morgen" der Samstag — an zwei von sieben Tagen falsch.
        const titel = zweiteUeberschrift({ datum: "2026-09-21" })
        expect(titel).toContain("Nächster Schultag")
        expect(titel).not.toContain("Morgen")
    })

    it("nennt das Datum", () => {
        expect(zweiteUeberschrift({ datum: "2026-09-21" })).toMatch(/21\.09/)
    })

    it("hat einen eigenen Satz fürs Schuljahresende", () => {
        expect(KEIN_NAECHSTER).toContain("Schuljahr")
    })
})

describe("stundenZeile", () => {
    it("nennt die Stunde zuerst", () => {
        const zeile = stundenZeile({ stunde: "3.–4. Stunde", gruppe: "9C", thema: "Mol" })
        expect(zeile.startsWith("3.–4. Stunde")).toBe(true)
        expect(zeile).toContain("9C")
        expect(zeile).toContain("Mol")
    })

    it("nimmt die Einheit, wenn kein Thema dasteht", () => {
        const zeile = stundenZeile({ stunde: "1. Stunde", gruppe: "9C", ue_titel: "Stoffmenge" })
        expect(zeile).toContain("Stoffmenge")
    })

    it("erfindet keinen Platzhalter", () => {
        const zeile = stundenZeile({ stunde: "1. Stunde", gruppe: "9C" })
        expect(zeile).toBe("1. Stunde · 9C")
    })
})

describe("kennzeichen", () => {
    it("benennt Ausfall und Vertretung", () => {
        expect(kennzeichen({ kategorie: "ausfall" })).toBe("Ausfall")
        expect(kennzeichen({ kategorie: "vertretung" })).toBe("Vertretung")
    })

    it("schweigt bei regulärem Unterricht", () => {
        expect(kennzeichen({ kategorie: "unterricht" })).toBeNull()
    })
})

describe("naechsterSchritt", () => {
    it("bietet ohne Einheit keinen Entwurf an", () => {
        // ⚠️ Der Endpunkt hängt an der Unterrichtseinheit. Eine Schaltfläche, die 404
        // antwortet, wäre schlimmer als keine.
        const schritt = naechsterSchritt({ hat_entwurf: false, ue_node_id: null })
        expect(schritt.moeglich).toBe(false)
        expect(schritt.text).toContain("Einheit")
    })

    it("unterscheidet öffnen und anlegen", () => {
        expect(naechsterSchritt({ hat_entwurf: true }).text).toContain("öffnen")
        expect(naechsterSchritt({ hat_entwurf: false, ue_node_id: "x" }).text).toContain("anlegen")
    })
})

describe("plannerLink", () => {
    it("baut den Weg in die Planung", () => {
        expect(plannerLink({ subject_slug: "chemie", group_id: 7 }))
            .toBe("/subjects/chemie/groups/7/planner")
    })

    it("liefert keinen Link ohne Fach", () => {
        // ⚠️ Sonst entstünde `/subjects/null/...` — ein Link, der aussieht, als führe er
        // irgendwohin.
        expect(plannerLink({ subject_slug: null, group_id: 7 })).toBeNull()
    })
})

describe("offeneEntscheidungen", () => {
    it("fasst beide Quellen zusammen", () => {
        // Die Lehrkraft will wissen, ob etwas wartet — nicht, aus welcher Quelle.
        expect(offeneEntscheidungen(2, 1)).toContain("3")
    })

    it("schweigt, wenn nichts offen ist", () => {
        expect(offeneEntscheidungen(0, 0)).toBeNull()
        expect(offeneEntscheidungen()).toBeNull()
    })

    it("formuliert die Einzahl richtig", () => {
        expect(offeneEntscheidungen(1, 0)).toContain("1 Gruppe wartet")
    })
})
