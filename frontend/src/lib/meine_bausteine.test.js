import { describe, it, expect } from "vitest"
import {
  aufmerksamkeitsText,
  nurAufmerksamkeit,
  ablaufAnzeige,
  abschnittsTitel,
  nachTypGefiltert,
  tageBisAblauf,
  vorkommendeTypen,
} from "./meine_bausteine.js"

const HEUTE = new Date(2026, 8, 5) // 05.09.2026, lokal

describe("tageBisAblauf", () => {
  it("zählt Kalendertage bis zum Datum", () => {
    expect(tageBisAblauf("2026-09-08", HEUTE)).toBe(3)
  })

  it("gibt heute als 0 zurück", () => {
    expect(tageBisAblauf("2026-09-05", HEUTE)).toBe(0)
  })

  it("wird negativ, wenn das Datum vorbei ist", () => {
    expect(tageBisAblauf("2026-09-01", HEUTE)).toBe(-4)
  })

  it("rechnet in Kalendertagen, nicht in 24-Stunden-Schritten", () => {
    // Sonst spränge die Zahl im Tagesverlauf: um 23 Uhr wäre „morgen" plötzlich 0.
    const spaetAbends = new Date(2026, 8, 5, 23, 30)
    expect(tageBisAblauf("2026-09-06", spaetAbends)).toBe(1)
    const frueh = new Date(2026, 8, 5, 0, 30)
    expect(tageBisAblauf("2026-09-06", frueh)).toBe(1)
  })

  it("verträgt fehlende und unbrauchbare Daten", () => {
    expect(tageBisAblauf(null, HEUTE)).toBeNull()
    expect(tageBisAblauf("", HEUTE)).toBeNull()
    expect(tageBisAblauf("kein Datum", HEUTE)).toBeNull()
  })
})

describe("ablaufAnzeige", () => {
  it("ohne Datum bleibt die Spalte leer", () => {
    expect(ablaufAnzeige(null, HEUTE)).toEqual({ text: "", stufe: "keine" })
  })

  it("weit in der Zukunft ohne Warnung", () => {
    const a = ablaufAnzeige("2027-07-28", HEUTE)
    expect(a.stufe).toBe("keine")
    expect(a.text).toContain("läuft ab am")
  })

  it("innerhalb von 14 Tagen warnt es und nennt die Tage", () => {
    const a = ablaufAnzeige("2026-09-08", HEUTE)
    expect(a.stufe).toBe("warnung")
    expect(a.text).toContain("in 3 Tagen")
  })

  it("ein Tag steht im Singular", () => {
    expect(ablaufAnzeige("2026-09-06", HEUTE).text).toContain("in 1 Tag")
  })

  it("heute ist ein eigener Fall", () => {
    // „in 0 Tagen" wäre richtig gerechnet und trotzdem unlesbar.
    expect(ablaufAnzeige("2026-09-05", HEUTE)).toEqual({
      text: "läuft heute ab",
      stufe: "warnung",
    })
  })

  it("vergangenes Datum ist abgelaufen, nicht Warnung", () => {
    const a = ablaufAnzeige("2026-09-01", HEUTE)
    expect(a.stufe).toBe("abgelaufen")
    expect(a.text).toContain("abgelaufen am")
  })

  it("die Grenze liegt bei 14 Tagen", () => {
    expect(ablaufAnzeige("2026-09-19", HEUTE).stufe).toBe("warnung")
    expect(ablaufAnzeige("2026-09-20", HEUTE).stufe).toBe("keine")
  })
})

const DATEN = {
  abschnitte: [
    {
      fach: "Mathematik",
      subject_id: 1,
      anzahl: 2,
      bausteine: [
        { id: "a", title: "A", content_type: "arbeitsblatt" },
        { id: "b", title: "B", content_type: "aufgabe" },
      ],
    },
    {
      fach: null,
      subject_id: null,
      anzahl: 1,
      bausteine: [{ id: "c", title: "C", content_type: "arbeitsblatt" }],
    },
  ],
  gesamt: 3,
}

describe("vorkommendeTypen", () => {
  it("zählt über alle Abschnitte", () => {
    const typen = vorkommendeTypen(DATEN)
    expect(typen).toEqual([
      { typ: "arbeitsblatt", label: "arbeitsblatt", anzahl: 2 },
      { typ: "aufgabe", label: "aufgabe", anzahl: 1 },
    ])
  })

  it("sortiert nach Label, nicht nach Vorkommen", () => {
    const label = (t) => ({ arbeitsblatt: "Zettel", aufgabe: "Aufgabe" })[t] ?? t
    expect(vorkommendeTypen(DATEN, label).map((t) => t.label)).toEqual([
      "Aufgabe",
      "Zettel",
    ])
  })

  it("verträgt leere Daten", () => {
    expect(vorkommendeTypen(null)).toEqual([])
    expect(vorkommendeTypen({ abschnitte: [] })).toEqual([])
  })
})

describe("nachTypGefiltert", () => {
  it("ohne Typ bleibt alles", () => {
    expect(nachTypGefiltert(DATEN, null)).toBe(DATEN)
  })

  it("filtert und wirft leer gewordene Abschnitte weg", () => {
    const gefiltert = nachTypGefiltert(DATEN, "aufgabe")
    expect(gefiltert.abschnitte).toHaveLength(1)
    expect(gefiltert.abschnitte[0].fach).toBe("Mathematik")
    expect(gefiltert.gesamt).toBe(1)
  })

  it("zieht die Abschnittszähler nach", () => {
    // Sonst stünde am Abschnitt „2", während eine Zeile darunter steht.
    const gefiltert = nachTypGefiltert(DATEN, "arbeitsblatt")
    expect(gefiltert.abschnitte.map((a) => a.anzahl)).toEqual([1, 1])
  })

  it("lässt die Vorlage unverändert", () => {
    nachTypGefiltert(DATEN, "aufgabe")
    expect(DATEN.abschnitte[0].bausteine).toHaveLength(2)
  })
})

describe("abschnittsTitel", () => {
  it("nimmt den Fachnamen", () => {
    expect(abschnittsTitel({ fach: "Physik" })).toBe("Physik")
  })

  it("ohne Fach steht „Ohne Fach“", () => {
    expect(abschnittsTitel({ fach: null })).toBe("Ohne Fach")
    expect(abschnittsTitel(null)).toBe("Ohne Fach")
  })
})

describe("aufmerksamkeitsText", () => {
  const leer = {
    gesamt: 0, laeuft_bald_ab: 0, abgelaufen: 0,
    archivierte_referenzen: 0, unvollstaendig: 0,
  }

  it("ohne Anlass kein Text — und damit kein Banner", () => {
    expect(aufmerksamkeitsText(leer)).toBe("")
    expect(aufmerksamkeitsText(null)).toBe("")
  })

  it("nennt nur belegte Kategorien", () => {
    // „0 sind abgelaufen" liest sich wie ein Vorwurf und verlängert den Satz.
    const text = aufmerksamkeitsText({ ...leer, gesamt: 1, archivierte_referenzen: 1 })
    expect(text).toBe("1 Baustein braucht Aufmerksamkeit: 1 verweist auf archivierte Bausteine")
    expect(text).not.toContain("abgelaufen")
  })

  it("setzt Singular und Plural je Kategorie", () => {
    expect(aufmerksamkeitsText({ ...leer, gesamt: 2, laeuft_bald_ab: 2 }))
      .toBe("2 Bausteine brauchen Aufmerksamkeit: 2 laufen bald ab")
    expect(aufmerksamkeitsText({ ...leer, gesamt: 1, laeuft_bald_ab: 1 }))
      .toBe("1 Baustein braucht Aufmerksamkeit: 1 läuft bald ab")
  })

  it("reiht mehrere Kategorien auf", () => {
    const text = aufmerksamkeitsText({
      gesamt: 4, laeuft_bald_ab: 1, abgelaufen: 2,
      archivierte_referenzen: 1, unvollstaendig: 3,
    })
    expect(text).toBe(
      "4 Bausteine brauchen Aufmerksamkeit: 1 läuft bald ab, 2 sind abgelaufen, " +
      "1 verweist auf archivierte Bausteine, 3 sind unvollständig",
    )
  })

  it("gesamt ist nicht die Summe — Mehrfachbetroffene zählen einmal", () => {
    // 1 Baustein, der zugleich abgelaufen ist und auf Archiviertes verweist.
    const text = aufmerksamkeitsText({
      ...leer, gesamt: 1, abgelaufen: 1, archivierte_referenzen: 1,
    })
    expect(text.startsWith("1 Baustein braucht")).toBe(true)
  })
})

describe("nurAufmerksamkeit", () => {
  const DATEN_MIT = {
    abschnitte: [
      {
        fach: "Chemie", subject_id: 3, anzahl: 2,
        bausteine: [
          { id: "a", title: "Ohne", kategorien: [] },
          { id: "b", title: "Mit", kategorien: ["archivierte_referenzen"] },
        ],
      },
      {
        fach: null, subject_id: null, anzahl: 1,
        bausteine: [{ id: "c", title: "Auch ohne", kategorien: [] }],
      },
    ],
    gesamt: 3,
  }

  it("behält nur markierte Bausteine", () => {
    const g = nurAufmerksamkeit(DATEN_MIT)
    expect(g.abschnitte).toHaveLength(1)
    expect(g.abschnitte[0].bausteine.map((b) => b.title)).toEqual(["Mit"])
  })

  it("zieht Gesamtzahl und Abschnittszähler nach", () => {
    const g = nurAufmerksamkeit(DATEN_MIT)
    expect(g.gesamt).toBe(1)
    expect(g.abschnitte[0].anzahl).toBe(1)
  })

  it("lässt die Vorlage unverändert", () => {
    nurAufmerksamkeit(DATEN_MIT)
    expect(DATEN_MIT.abschnitte).toHaveLength(2)
  })

  it("verträgt fehlende kategorien", () => {
    const g = nurAufmerksamkeit({ abschnitte: [{ bausteine: [{ id: "x" }] }] })
    expect(g.abschnitte).toEqual([])
  })
})
