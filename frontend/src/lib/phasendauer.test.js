import { describe, it, expect } from "vitest"
import { dauerAusEingabe, dauerZusatz, geplanteMinuten, istGestrichen, startzeiten, zeitspanne } from "./phasendauer.js"

describe("phasendauer — Phasen ohne Dauer (0.13, P1)", () => {
    it("ein geleertes Feld speichert null, keine 1", () => {
        expect(dauerAusEingabe("")).toBeNull()
        expect(dauerAusEingabe("  ")).toBeNull()
        expect(dauerAusEingabe(undefined)).toBeNull()
    })

    it("eine Angabe bleibt zwischen 1 und 480 — 0 gibt es nicht", () => {
        expect(dauerAusEingabe("15")).toBe(15)
        expect(dauerAusEingabe("0")).toBe(1)
        expect(dauerAusEingabe("999")).toBe(480)
    })

    it("die Zeitspalte zeigt ohne Dauer nur den Beginn", () => {
        expect(zeitspanne(10, 15)).toBe("10–25′")
        expect(zeitspanne(10, null)).toBe("ab 10′")
        expect(zeitspanne(10, undefined)).toBe("ab 10′")
    })

    it("der Prompt nennt eine Dauer nur, wenn es eine gibt", () => {
        expect(dauerZusatz(15)).toBe(" (15′)")
        expect(dauerZusatz(null)).toBe("")
    })

    it("nach einer Phase ohne Dauer steht die Uhr — auch für alle folgenden", () => {
        const phasen = [{ dauer_min: 10 }, { dauer_min: null }, { dauer_min: 10 }, { dauer_min: 5 }]
        expect(startzeiten(phasen)).toEqual([0, 10, null, null])
        expect(startzeiten(phasen).map((b, i) => zeitspanne(b, phasen[i].dauer_min)))
            .toEqual(["0–10′", "ab 10′", "–", "–"])
    })

    it("ohne fehlende Dauer zählt die Uhr wie bisher", () => {
        expect(startzeiten([{ dauer_min: 10 }, { dauer_min: 15 }, { dauer_min: 5 }])).toEqual([0, 10, 25])
        expect(startzeiten([])).toEqual([])
    })
})

describe("phasendauer — gestrichene Phasen (0.19)", () => {
    const phasen = [
        { id: "a", dauer_min: 15 },
        { id: "b", dauer_min: 30, status: "gestrichen" },
        { id: "c", dauer_min: 10, status: "offen" },
        { id: "d", dauer_min: 5 },
    ]

    it("zeigt „–“ und die Uhr läuft ohne sie weiter", () => {
        // Bis 0.19: [0, 15, 45, 55] — die gestrichene schob alles nach hinten.
        expect(startzeiten(phasen)).toEqual([0, null, 15, 25])
        expect(startzeiten(phasen).map((b, i) => zeitspanne(b, phasen[i].dauer_min)))
            .toEqual(["0–15′", "–", "15–25′", "25–30′"])
    })

    it("zählt nicht zu den geplanten Minuten, „offen“ schon", () => {
        expect(geplanteMinuten(phasen)).toBe(30)
        expect(geplanteMinuten([])).toBe(0)
    })

    it("folgt in der Nachbereitung dem gewählten Status", () => {
        const gewaehlt = { a: "gestrichen", b: "erledigt" }
        const statusVon = (p) => gewaehlt[p.id] ?? p.status
        expect(istGestrichen(phasen[0], statusVon)).toBe(true)
        expect(geplanteMinuten(phasen, statusVon)).toBe(45)
        expect(startzeiten(phasen, statusVon)).toEqual([null, 0, 30, 40])
    })
})
