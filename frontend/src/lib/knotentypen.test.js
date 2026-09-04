import { describe, it, expect } from "vitest"
import {
  auswaehlbareTypen,
  auswaehlbareTypLabels,
  auswaehlbareTypOptionen,
} from "./knotentypen.js"
import {
  CONTENT_TYPES,
  CONTENT_TYPE_LABELS,
  RUHENDE_CONTENT_TYPES,
} from "./taxonomy.js"

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

describe("auswaehlbareTypOptionen", () => {
  it("beschriftet deutsch und behält den Schlüssel als Wert", () => {
    const optionen = auswaehlbareTypOptionen(["arbeitsblatt", "klausur"])
    expect(optionen).toEqual([
      { key: "arbeitsblatt", label: CONTENT_TYPE_LABELS.arbeitsblatt },
      { key: "klausur", label: CONTENT_TYPE_LABELS.klausur },
    ])
  })

  it("zeigt nie einen rohen content_type", () => {
    // Der gemeldete Fehler: `schuelerpraesentation` statt „Schülerpräsentation" —
    // in drei Auswahlfeldern gleichzeitig.
    for (const typen of Object.values(CONTENT_TYPES)) {
      for (const { key, label } of auswaehlbareTypOptionen(typen)) {
        expect(label).not.toBe(key)
      }
    }
  })

  it("sortiert nach Label, nicht nach Schlüssel", () => {
    const labels = auswaehlbareTypOptionen(CONTENT_TYPES.knowledge).map((o) => o.label)
    expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b, "de")))
  })

  it("erbt die Ruhend-Regel samt Ausnahme", () => {
    expect(auswaehlbareTypOptionen(["arbeitsblatt", "lernplan"]).map((o) => o.key)).toEqual(
      ["arbeitsblatt"],
    )
    expect(
      auswaehlbareTypOptionen(["arbeitsblatt", "lernplan"], "lernplan").map((o) => o.key),
    ).toContain("lernplan")
  })

  it("verträgt null und undefined", () => {
    expect(auswaehlbareTypOptionen(null)).toEqual([])
    expect(auswaehlbareTypOptionen(undefined)).toEqual([])
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
