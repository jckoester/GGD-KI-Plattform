import { describe, it, expect } from "vitest"
import {
  aktionenFuer,
  aufmerksamkeitsText,
  loeschHindernis,
  nachEinsatzortGefiltert,
  nurAufmerksamkeit,
  CHIPS_JE_ZEILE,
  ORTE_ALS_CHIPS,
  gekappt,
  vorkommendeEinsatzorte,
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

describe("aktionenFuer", () => {
  it("aktiver Baustein: archivieren und Ablauf, kein Reaktivieren", () => {
    expect(aktionenFuer({ status: "active" })).toEqual({
      archivieren: true, reaktivieren: false, ablauf: true,
    })
  })

  it("archivierter Baustein: nur reaktivieren", () => {
    // Das Ablaufdatum am Archivierten zu ändern hilft nicht — er ist schon weg.
    expect(aktionenFuer({ status: "archived" })).toEqual({
      archivieren: false, reaktivieren: true, ablauf: false,
    })
  })

  it("verträgt fehlende Angaben", () => {
    expect(aktionenFuer(null).archivieren).toBe(true)
  })
})

describe("loeschHindernis", () => {
  it("liest die F7-Antwort des Servers", () => {
    const fehler = {
      detail: {
        grund: "referenziert",
        nachricht: "2 aktive Bausteine anderer verweisen auf diesen.",
        referenzen: [{ id: "a", title: "Curriculum" }, { id: "b", title: "Einheit" }],
      },
    }
    const h = loeschHindernis(fehler)
    expect(h.nachricht).toContain("2 aktive Bausteine")
    expect(h.referenzen).toHaveLength(2)
  })

  it("verträgt schlichten Fehlertext", () => {
    // Sonst stünde im Dialog „[object Object]" — oder gar nichts.
    const h = loeschHindernis({ detail: "Keine Berechtigung" })
    expect(h.nachricht).toBe("Keine Berechtigung")
    expect(h.referenzen).toEqual([])
  })

  it("verträgt einen Fehler ganz ohne detail", () => {
    expect(loeschHindernis(new Error("kaputt")).nachricht).toBe("kaputt")
    expect(loeschHindernis({}).nachricht).toContain("lässt sich nicht löschen")
  })
})

const MIT_EINSATZ = {
  abschnitte: [
    {
      fach: "Mathematik", subject_id: 1, anzahl: 3,
      bausteine: [
        { id: "a", title: "Blatt A", eingesetzt_in: [{ id: "s1", titel: "Stunde 1" }] },
        { id: "b", title: "Blatt B", eingesetzt_in: [
            { id: "s1", titel: "Stunde 1" }, { id: "s2", titel: "Stunde 2" }] },
        { id: "c", title: "Blatt C", eingesetzt_in: [] },
      ],
    },
  ],
  gesamt: 3,
}

describe("vorkommendeEinsatzorte", () => {
  it("zählt, in wie vielen Bausteinen ein Ort vorkommt", () => {
    expect(vorkommendeEinsatzorte(MIT_EINSATZ)).toEqual([
      { id: "s1", titel: "Stunde 1", anzahl: 2 },
      { id: "s2", titel: "Stunde 2", anzahl: 1 },
    ])
  })

  it("sortiert nach Häufigkeit, nicht alphabetisch", () => {
    // Bei hunderten Stunden im Jahr stünde alphabetisch vorn, was mit „A" anfängt.
    // Nützlich ist die Einheit, in der viel steckt.
    const daten = {
      abschnitte: [{ bausteine: [
        { id: "1", eingesetzt_in: [{ id: "z", titel: "Zwischenprüfung" }] },
        { id: "2", eingesetzt_in: [{ id: "z", titel: "Zwischenprüfung" }] },
        { id: "3", eingesetzt_in: [{ id: "a", titel: "Auftakt" }] },
      ] }],
    }
    expect(vorkommendeEinsatzorte(daten).map((o) => o.titel)).toEqual([
      "Zwischenprüfung", "Auftakt",
    ])
  })

  it("bei gleicher Zahl entscheidet der Titel — sonst springt die Reihenfolge", () => {
    const daten = {
      abschnitte: [{ bausteine: [
        { id: "1", eingesetzt_in: [{ id: "b", titel: "Beta" }] },
        { id: "2", eingesetzt_in: [{ id: "a", titel: "Alpha" }] },
      ] }],
    }
    expect(vorkommendeEinsatzorte(daten).map((o) => o.titel)).toEqual(["Alpha", "Beta"])
  })

  it("verträgt Bausteine ohne Einsatzort und leere Daten", () => {
    expect(vorkommendeEinsatzorte({ abschnitte: [{ bausteine: [{ id: "x" }] }] })).toEqual([])
    expect(vorkommendeEinsatzorte(null)).toEqual([])
  })
})

describe("nachEinsatzortGefiltert", () => {
  it("behält nur Bausteine dieses Orts", () => {
    const g = nachEinsatzortGefiltert(MIT_EINSATZ, "s2")
    expect(g.abschnitte[0].bausteine.map((b) => b.title)).toEqual(["Blatt B"])
    expect(g.gesamt).toBe(1)
  })

  it("ohne Ort bleibt alles", () => {
    expect(nachEinsatzortGefiltert(MIT_EINSATZ, null)).toBe(MIT_EINSATZ)
  })

  it("zieht den Abschnittszähler nach und lässt die Vorlage unberührt", () => {
    const g = nachEinsatzortGefiltert(MIT_EINSATZ, "s1")
    expect(g.abschnitte[0].anzahl).toBe(2)
    expect(MIT_EINSATZ.abschnitte[0].bausteine).toHaveLength(3)
  })
})

describe("gekappt", () => {
  const liste = ["a", "b", "c", "d", "e"]

  it("zeigt bis zum Deckel und zählt den Rest", () => {
    expect(gekappt(liste, 3)).toEqual({
      sichtbar: ["a", "b", "c"], rest: ["d", "e"], weitere: 2,
    })
  })

  it("unter dem Deckel bleibt alles sichtbar", () => {
    expect(gekappt(["a"], 3)).toEqual({ sichtbar: ["a"], rest: [], weitere: 0 })
  })

  it("verträgt leere und fehlende Listen", () => {
    expect(gekappt([], 3).weitere).toBe(0)
    expect(gekappt(null, 3)).toEqual({ sichtbar: [], rest: [], weitere: 0 })
  })

  it("die Deckel sind bewusst verschieden gewählt", () => {
    // Eine Tabellenzeile ist schmal, die Filterleiste hat eine ganze Breite.
    expect(CHIPS_JE_ZEILE).toBeLessThan(ORTE_ALS_CHIPS)
  })
})
