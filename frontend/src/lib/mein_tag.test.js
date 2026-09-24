import { describe, it, expect } from "vitest"
import {
    KEIN_NAECHSTER,
    kennzeichen,
    leerFuehrtZurEinrichtung,
    leerSatz,
    einheitHinweis,
    offeneEntscheidungen,
    plannerLink,
    stundenTitel,
    stundenVorspann,
    stundenZeile,
    titelAktion,
    titelText,
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
        const zeile = stundenZeile({ stunde: "3.–4.", gruppe: "9C", thema: "Mol" })
        expect(zeile.startsWith("3.–4.")).toBe(true)
        expect(zeile).toContain("9C")
        expect(zeile).toContain("Mol")
    })

    it("nimmt die Einheit, wenn kein Thema dasteht", () => {
        const zeile = stundenZeile({ stunde: "1.", gruppe: "9C", ue_titel: "Stoffmenge" })
        expect(zeile).toContain("Stoffmenge")
    })

    it("erfindet keinen Platzhalter", () => {
        const zeile = stundenZeile({ stunde: "1.", gruppe: "9C" })
        expect(zeile).toBe("1. · 9C")
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

describe("titelAktion", () => {
    const gruppe = { subject_slug: "chemie", group_id: 7, slot_id: "s1" }

    it("führt in den vorhandenen Entwurf", () => {
        expect(titelAktion({ ...gruppe, stunde_node_id: "abc" })).toEqual({
            ziel: "/subjects/chemie/groups/7/planner/lessons/abc",
            slotId: null,
        })
    })

    it("hält ohne Entwurf ein echtes Ziel bereit — und den Auftrag anzulegen", () => {
        // `ziel` ist der Weg für Mittelklick und „in neuem Tab öffnen"; `slotId` sagt der
        // Oberfläche, dass der gewöhnliche Klick es besser kann: anlegen und hineinspringen.
        expect(titelAktion({ ...gruppe, ue_node_id: null })).toEqual({
            ziel: "/subjects/chemie/groups/7/planner",
            slotId: "s1",
        })
    })

    it("⚠️ gibt in **jedem** Zustand ein Ziel — nie einen toten Titel", () => {
        // Der eigentliche Wächter. Hier ist am 24.09.2026 zweimal ein toter Titel
        // entstanden: erst weil `stunde_node_id` in der API-Antwort fehlte, dann weil das
        // Markup ihn als `<button>` rendelte, den die Ellipsis verschluckte. Ein Test je
        // Einzelfall hätte beides durchgelassen — dieser geht den Zustandsraum ab.
        for (const stunde_node_id of [null, "abc"]) {
            for (const ue_node_id of [null, "ue1"]) {
                for (const thema of [null, "Titration"]) {
                    const a = titelAktion({ ...gruppe, stunde_node_id, ue_node_id, thema })
                    expect(a?.ziel, JSON.stringify({ stunde_node_id, ue_node_id, thema }))
                        .toBeTruthy()
                }
            }
        }
    })

    it("baut ohne Fach gar keinen Weg", () => {
        // Lieber kein Link als `/subjects/null/…`, der aussieht, als führte er irgendwohin.
        expect(titelAktion({ subject_slug: null, group_id: 7, slot_id: "s1" })).toBeNull()
    })

    it("verlinkt ohne Termin, ohne zum Anlegen aufzufordern", () => {
        const a = titelAktion({ subject_slug: "chemie", group_id: 7 })
        expect(a.ziel).toBe("/subjects/chemie/groups/7/planner")
        expect(a.slotId).toBeNull()
    })
})

describe("titelText", () => {
    it("nimmt Thema oder Einheit, wenn es eines gibt", () => {
        expect(titelText({ thema: "Titration" })).toBe("Titration")
        expect(titelText({ ue_titel: "Säuren" })).toBe("Säuren")
    })

    it("beschreibt die Lücke, statt zum Handeln aufzufordern", () => {
        // ⚠️ An der Stelle des Titels gehört eine Beschreibung. „Stunde planen" las sich
        // wie der Titel der Stunde und drängte sich vor das, was man eigentlich sucht.
        expect(titelText({})).toBe("ohne Thema")
    })
})

describe("einheitHinweis", () => {
    const gruppe = { subject_slug: "chemie", group_id: 7 }

    it("führt ohne Einheit in die Jahresplanung", () => {
        // Ein Hinweis **ohne Weg** wäre eine Sackgasse: Man weiß, was fehlt, nicht wohin.
        const h = einheitHinweis({ ...gruppe, ue_node_id: null })
        expect(h.text).toContain("Einheit")
        expect(h.ziel).toBe("/subjects/chemie/groups/7/planner")
    })

    it("schweigt, wenn die Einheit steht", () => {
        expect(einheitHinweis({ ...gruppe, ue_node_id: "x" })).toBeNull()
    })

    it("sagt nichts mehr über den Entwurf", () => {
        // Der Titel erreicht ihn in jedem Zustand selbst. Zwei Bedienelemente derselben
        // Zeile, die dasselbe tun, sind keine Hilfe, sondern eine Frage.
        const h = einheitHinweis({ ...gruppe, ue_node_id: null, stunde_node_id: null })
        expect(h.text).not.toContain("Entwurf")
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

describe("stundenVorspann und stundenTitel", () => {
    it("trennt, was verlinkt wird, von dem was nicht verlinkt wird", () => {
        // Der Titel führt in den Stundenentwurf; Stunde und Gruppe bleiben Text, damit
        // die Zeile keine große Schaltfläche wird.
        const s = { stunde: "3.–4.", gruppe: "9C", thema: "Mol" }
        expect(stundenVorspann(s)).toBe("3.–4. · 9C")
        expect(stundenTitel(s)).toBe("Mol")
    })

    it("nimmt die Einheit, wenn kein Thema dasteht", () => {
        expect(stundenTitel({ ue_titel: "Stoffmenge" })).toBe("Stoffmenge")
    })

    it("erfindet keinen Titel", () => {
        expect(stundenTitel({ stunde: "1.", gruppe: "9C" })).toBeNull()
    })
})
