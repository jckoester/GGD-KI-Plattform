import { describe, it, expect } from "vitest"
import { auswaehlbareTypen, auswaehlbareTypLabels } from "./knotentypen.js"
import { CONTENT_TYPES, RUHENDE_CONTENT_TYPES } from "./taxonomy.js"

describe("auswaehlbareTypen", () => {
  it("entfernt ruhende Typen", () => {
    const typen = ["arbeitsblatt", "lernplan", "klausur"]
    expect(auswaehlbareTypen(typen)).toEqual(["arbeitsblatt", "klausur"])
  })

  it("lässt aktive Typen unangetastet", () => {
    const typen = ["arbeitsblatt", "klausur", "aufgabe"]
    expect(auswaehlbareTypen(typen)).toEqual(typen)
  })

  it("behält den aktuellen Typ, auch wenn er ruht", () => {
    // Der Fall, der sonst still Daten verändert: Wer einen ruhenden Knoten
    // bearbeitet, fände ein leeres Auswahlfeld vor und speicherte einen anderen Typ.
    expect(auswaehlbareTypen(["arbeitsblatt", "lernplan"], "lernplan")).toEqual([
      "arbeitsblatt",
      "lernplan",
    ])
  })

  it("behält den aktuellen Typ nur, wenn er in der Liste steht", () => {
    expect(auswaehlbareTypen(["arbeitsblatt"], "lernplan")).toEqual(["arbeitsblatt"])
  })

  it("verträgt null und undefined", () => {
    expect(auswaehlbareTypen(null)).toEqual([])
    expect(auswaehlbareTypen(undefined)).toEqual([])
  })

  it("die Artefakt-Kategorie verliert genau ihre ruhenden Typen", () => {
    const alle = CONTENT_TYPES.artifact
    const uebrig = auswaehlbareTypen(alle)
    const entfernt = alle.filter((t) => !uebrig.includes(t))
    expect(entfernt.every((t) => RUHENDE_CONTENT_TYPES.has(t))).toBe(true)
    expect(uebrig.some((t) => RUHENDE_CONTENT_TYPES.has(t))).toBe(false)
  })
})

describe("auswaehlbareTypLabels", () => {
  it("liefert Paare aus Schlüssel und Label ohne ruhende Typen", () => {
    const paare = auswaehlbareTypLabels()
    expect(paare.length).toBeGreaterThan(0)
    expect(paare.every(([key]) => !RUHENDE_CONTENT_TYPES.has(key))).toBe(true)
    expect(paare.every(([, label]) => typeof label === "string" && label.length > 0)).toBe(
      true,
    )
  })

  it("behält einen gesetzten ruhenden Filterwert", () => {
    const ruhend = [...RUHENDE_CONTENT_TYPES][0]
    const paare = auswaehlbareTypLabels(ruhend)
    expect(paare.map(([key]) => key)).toContain(ruhend)
  })
})

describe("Taxonomie-Zusicherungen", () => {
  it("die Schüler-Artefakte ruhen, bis es einen Übernahme-Weg gibt", () => {
    for (const typ of [
      "lernplan",
      "schuelertext",
      "schuelerpraesentation",
      "strukturierung",
      "feedback_text",
    ]) {
      expect(RUHENDE_CONTENT_TYPES.has(typ)).toBe(true)
    }
  })

  it("die tragenden Typen ruhen nicht", () => {
    for (const typ of ["arbeitsblatt", "ik_kompetenz", "methode", "begriff", "operator"]) {
      expect(RUHENDE_CONTENT_TYPES.has(typ)).toBe(false)
    }
  })
})
