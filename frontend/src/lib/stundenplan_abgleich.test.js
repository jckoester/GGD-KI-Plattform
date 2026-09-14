import { describe, it, expect } from "vitest"
import { fehlendesRaster, rasterJeGruppe, OHNE_SLOT } from "./stundenplan_abgleich.js"

const ohneSlot = (n) =>
    Array.from({ length: n }, (_, i) => ({
        datum: "2026-09-14", stunde: i + 1, grund: OHNE_SLOT,
        beschreibung: "Stundenplan kennt Unterricht, die Jahresplanung hat dort keinen Slot.",
    }))

describe("fehlendesRaster", () => {
    it("erkennt die leere Jahresplanung", () => {
        const meldung = fehlendesRaster({ geaendert: 0, konflikte: ohneSlot(48) })
        expect(meldung).toMatch(/keine Stunden angelegt/)
        expect(meldung).toMatch(/Aus Stundenplan übernehmen/)
    })

    it("schweigt, wenn es nichts zu melden gibt", () => {
        expect(fehlendesRaster({ geaendert: 0, konflikte: [] })).toBeNull()
        expect(fehlendesRaster({ geaendert: 3, konflikte: [] })).toBeNull()
        expect(fehlendesRaster(null)).toBeNull()
        expect(fehlendesRaster({})).toBeNull()
    })

    it("verdeckt keine echten Befunde", () => {
        // Ein gemischtes Ergebnis ist kein „leere Planung"-Fall: Dort stecken Hinweise,
        // die jemand lesen soll — etwa eine festgehaltene Stunde, die der Abgleich nicht
        // anfassen durfte.
        const gemischt = [...ohneSlot(2), { grund: "pinned", beschreibung: "…" }]
        expect(fehlendesRaster({ geaendert: 0, konflikte: gemischt })).toBeNull()
    })

    it("schweigt, sobald etwas geändert wurde", () => {
        // Dann hat der Abgleich gearbeitet; die übrigen „kein Slot"-Hinweise betreffen
        // einzelne Stunden, nicht die ganze Gruppe.
        expect(fehlendesRaster({ geaendert: 1, konflikte: ohneSlot(5) })).toBeNull()
    })

    it("schweigt bei erkannten Verlegungen", () => {
        // Eine Verlegung setzt voraus, dass es Slots gibt — dann ist die Planung nicht leer.
        expect(
            fehlendesRaster({
                geaendert: 0,
                konflikte: ohneSlot(3),
                verlegungen: [{ von_datum: "2026-09-14", nach_datum: "2026-09-15" }],
            }),
        ).toBeNull()
    })
})

describe("rasterJeGruppe", () => {
    const muster = (group_id, gruppe, weekday, sicher = true) => ({
        group_id, gruppe, weekday, start_period: 1, periods: 1,
        rhythmus: "woechentlich", sicher,
    })

    it("bündelt die flache Liste nach Gruppen", () => {
        const r = rasterJeGruppe({
            patterns: [
                muster(7, "Mathe 8a", 0),
                muster(7, "Mathe 8a", 2),
                muster(9, "Chemie KS", 1),
            ],
        })
        expect(r.map((g) => g.group_id)).toEqual([9, 7])  // alphabetisch nach Gruppenname
        expect(r.find((g) => g.group_id === 7).zeilen).toHaveLength(2)
    })

    it("lässt Zeilen ohne Gruppe weg", () => {
        // Lerngruppen aus dem Stundenplan, die es auf der Plattform nicht gibt —
        // dorthin lässt sich nichts schreiben.
        const r = rasterJeGruppe({
            patterns: [muster(null, "NwT 9a/9c", 0), muster(7, "Mathe 8a", 0)],
        })
        expect(r).toHaveLength(1)
        expect(r[0].group_id).toBe(7)
    })

    it("zählt die unsicheren Zeilen je Gruppe", () => {
        const r = rasterJeGruppe({
            patterns: [muster(7, "Mathe 8a", 0), muster(7, "Mathe 8a", 2, false)],
        })
        expect(r[0].unsicher).toBe(1)
    })

    it("verträgt eine leere Antwort", () => {
        expect(rasterJeGruppe(null)).toEqual([])
        expect(rasterJeGruppe({})).toEqual([])
        expect(rasterJeGruppe({ patterns: [] })).toEqual([])
    })
})
