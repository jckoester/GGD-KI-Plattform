import { describe, it, expect } from "vitest"
import {
  alleSammlungen,
  fachSammlungen,
  istStub,
  kannVerknuepfen,
  relationen,
  kategorieVon,
  sidebarSammlungen,
  contentFeld,
  feldSchema,
  filter,
  metadatenAusFormular,
  pruefeEntwurf,
  sammlung,
  spalten,
  zellenwert,
} from "./collections.js"

describe("alleSammlungen", () => {
  it("liefert die fünf ersten Sammlungen mit Label und Beschreibungssatz", () => {
    const typen = alleSammlungen().map((s) => s.typ)
    expect(typen).toEqual([
      "methodenblatt",
      "operatorenblatt",
      "methode",
      "sozialform",
      "begriff",
    ])
    expect(alleSammlungen().every((s) => s.label && s.beschreibung)).toBe(true)
  })

  it("gibt Fachbegriff ein lesbares Label, nicht den Schlüssel", () => {
    const b = alleSammlungen().find((s) => s.typ === "begriff")
    expect(b.label).toBe("Fachbegriff")
  })
})

describe("sammlung", () => {
  it("kennt einen Typ ohne Sammlung nicht", () => {
    // `arbeitsblatt` ist ein gültiger Typ, hat aber keine gepflegte Ansicht.
    expect(sammlung("arbeitsblatt")).toBeNull()
    expect(sammlung("gibt_es_nicht")).toBeNull()
  })
})

describe("spalten", () => {
  it("mischt feste Spalten und Metadatenfelder", () => {
    const s = spalten("begriff")
    expect(s.map((c) => c.name)).toEqual([
      "titel",
      "fach",
      "ab_klasse",
      "status",
      "geaendert",
    ])
    const abKlasse = s.find((c) => c.name === "ab_klasse")
    expect(abKlasse.fest).toBe(false)
    expect(abKlasse.label).toBe("Ab Klassenstufe")
    expect(abKlasse.typ).toBe("int")
  })

  it("beschriftet feste Spalten selbst", () => {
    expect(spalten("begriff").find((c) => c.name === "geaendert").label).toBe(
      "Zuletzt geändert",
    )
  })

  it("liefert für einen Typ ohne Sammlung nichts", () => {
    expect(spalten("arbeitsblatt")).toEqual([])
  })
})

describe("filter", () => {
  it("bietet bei sozialform keinen Fachfilter — der Typ ist fachneutral", () => {
    expect(filter("sozialform")).not.toContain("fach")
    expect(filter("begriff")).toContain("fach")
  })
})

describe("zellenwert", () => {
  const node = {
    title: "Energie",
    status: "active",
    updated_at: "2026-09-02T10:00:00Z",
    metadata: { ab_klasse: 7 },
  }
  const [titel, fach, abKlasse, status, geaendert] = spalten("begriff")

  it("liest den Titel", () => {
    expect(zellenwert(node, titel)).toBe("Energie")
  })

  it("nimmt den Fachnamen von außen — die Liste kennt nur subject_id", () => {
    expect(zellenwert(node, fach, { fachname: "Physik" })).toBe("Physik")
  })

  it("zeigt fehlendes Fach als Gedankenstrich, nicht als Lücke", () => {
    // Bei `methode` ist „fachübergreifend" der Normalfall, kein fehlender Wert.
    expect(zellenwert(node, fach)).toBe("—")
  })

  it("übersetzt den Status", () => {
    expect(zellenwert(node, status)).toBe("aktiv")
    expect(zellenwert({ ...node, status: "archived" }, status)).toBe("archiviert")
  })

  it("formatiert das Datum deutsch", () => {
    expect(zellenwert(node, geaendert)).toMatch(/^\d{2}\.\d{2}\.\d{4}$/)
  })

  it("liest Metadatenfelder", () => {
    expect(zellenwert(node, abKlasse)).toBe("7")
  })

  it("fügt Listen zusammen", () => {
    const [, , aliase] = spalten("methode")
    expect(zellenwert({ metadata: { aliase: ["A", "B"] } }, aliase)).toBe("A, B")
  })

  it("zeigt leere Metadaten als Gedankenstrich", () => {
    expect(zellenwert({ metadata: {} }, abKlasse)).toBe("—")
    expect(zellenwert({}, abKlasse)).toBe("—")
  })
})

describe("contentFeld", () => {
  it("heißt bei begriff „Definition“ und ist Pflicht", () => {
    const f = contentFeld("begriff")
    expect(f.label).toBe("Definition")
    expect(f.pflicht).toBe(true)
    expect(f.hinweis).toMatch(/auffindbar/)
  })

  it("ist bei sozialform freiwillig", () => {
    expect(contentFeld("sozialform").pflicht).toBe(false)
  })
})

describe("pruefeEntwurf", () => {
  it("verlangt einen Titel", () => {
    expect(pruefeEntwurf("begriff", { content: "x" }).title).toBeTruthy()
    expect(pruefeEntwurf("begriff", { title: "   ", content: "x" }).title).toBeTruthy()
  })

  it("verlangt den Pflichttext und nennt ihn beim Namen", () => {
    const f = pruefeEntwurf("begriff", { title: "Energie" })
    expect(f.content).toContain("Definition")
  })

  it("lässt den Text weg, wo er freiwillig ist", () => {
    expect(pruefeEntwurf("sozialform", { title: "Plenum" })).toEqual({})
  })

  it("prüft den Zahlenbereich — dieselben Grenzen wie das Backend", () => {
    const entwurf = (v) => ({ title: "E", content: "d", metadata: { ab_klasse: v } })
    expect(pruefeEntwurf("begriff", entwurf(7))).toEqual({})
    expect(pruefeEntwurf("begriff", entwurf(0)).ab_klasse).toContain("mindestens 1")
    expect(pruefeEntwurf("begriff", entwurf(14)).ab_klasse).toContain("höchstens 13")
    expect(pruefeEntwurf("begriff", entwurf("sieben")).ab_klasse).toContain("ganze Zahl")
  })

  it("lässt optionale Felder leer", () => {
    expect(
      pruefeEntwurf("begriff", { title: "E", content: "d", metadata: { ab_klasse: "" } }),
    ).toEqual({})
  })

  it("prüft Auswahlfelder gegen ihre Werte", () => {
    const f = pruefeEntwurf("strukturierung", {
      title: "Gliederung", metadata: { form: "skizze" },
    })
    expect(f.form).toBeTruthy()
  })
})

describe("metadatenAusFormular", () => {
  it("wandelt Zahlenfelder in Zahlen", () => {
    expect(metadatenAusFormular("begriff", { ab_klasse: "7" })).toEqual({ ab_klasse: 7 })
  })

  it("lässt leere Felder weg statt sie als Leerstring zu schicken", () => {
    expect(metadatenAusFormular("begriff", { ab_klasse: "" })).toEqual({})
    expect(metadatenAusFormular("methode", { aliase: [] })).toEqual({})
  })

  it("entfernt ein geleertes Feld auch aus bestehenden Metadaten", () => {
    expect(metadatenAusFormular("begriff", { ab_klasse: "" }, { ab_klasse: 7 })).toEqual({})
  })

  it("lässt fremde Metadaten unangetastet", () => {
    // `metadata` ist ein freies Feld — der Editor darf nicht wegwerfen, was er nicht kennt.
    expect(
      metadatenAusFormular("begriff", { ab_klasse: 7 }, { quelle: "Duden" }),
    ).toEqual({ quelle: "Duden", ab_klasse: 7 })
  })
})

describe("feldSchema", () => {
  it("gilt auch für Typen ohne Sammlung", () => {
    // `strukturierung` ruht bis 0.9, seine Feldregel gilt trotzdem.
    expect(sammlung("strukturierung")).toBeNull()
    expect(feldSchema("strukturierung").form.werte).toEqual(["gliederung", "mindmap"])
  })
})

describe("kategorieVon", () => {
  it("kennt die Kategorie jeder Sammlung — sie liegen in dreien", () => {
    // ⚠️ Der Editor schrieb im ersten Entwurf `knowledge` fest und scheiterte mit 422.
    expect(kategorieVon("begriff")).toBe("concept")
    expect(kategorieVon("methodenblatt")).toBe("document")
    expect(kategorieVon("operatorenblatt")).toBe("document")
    expect(kategorieVon("methode")).toBe("knowledge")
    expect(kategorieVon("sozialform")).toBe("knowledge")
  })

  it("liefert für jede Sammlung eine Kategorie", () => {
    for (const s of alleSammlungen()) {
      expect(kategorieVon(s.typ)).toBeTruthy()
    }
  })

  it("gibt null für einen unbekannten Typ", () => {
    expect(kategorieVon("gibt_es_nicht")).toBeNull()
  })
})

describe("sidebarSammlungen", () => {
  it("führt nur, was situationsunabhängig interessiert", () => {
    // Entscheidung Jan, 02.09.2026: Methode und Sozialform sind fachneutral bzw. teils
    // fachübergreifend; Fachbegriffe anderer Fächer sind ebenfalls von Interesse
    // („was heißt Energie in Biologie?").
    expect(sidebarSammlungen().map((s) => s.typ)).toEqual([
      "methode",
      "sozialform",
      "begriff",
    ])
  })

  it("lässt die Blätter draußen — die sucht man mit einem Fach im Kopf", () => {
    const typen = sidebarSammlungen().map((s) => s.typ)
    expect(typen).not.toContain("methodenblatt")
    expect(typen).not.toContain("operatorenblatt")
  })

  it("nimmt nur ausdrücklich markierte Sammlungen auf", () => {
    // Vorgabe ist `false`: Eine neue Sammlung nistet sich nicht von selbst in der
    // Navigation ein.
    expect(sidebarSammlungen().length).toBeLessThan(alleSammlungen().length)
  })
})

describe("fachSammlungen", () => {
  it("sind die mit Fachfilter — abgeleitet, nicht konfiguriert", () => {
    expect(fachSammlungen().map((s) => s.typ)).toEqual([
      "methodenblatt",
      "operatorenblatt",
      "methode",
      "begriff",
    ])
  })

  it("lässt die fachneutrale Sozialform draußen", () => {
    // Sie stand bis 02.09.2026 fälschlich im Fachschafts-Abschnitt, obwohl der Typ
    // gar kein Fach kennt.
    expect(fachSammlungen().map((s) => s.typ)).not.toContain("sozialform")
  })

  it("überschneidet sich absichtlich mit der Sidebar", () => {
    // `methode` ist Mischtyp, `begriff` fachgebunden und trotzdem global interessant.
    const beides = fachSammlungen()
      .map((s) => s.typ)
      .filter((typ) => sidebarSammlungen().some((s) => s.typ === typ))
    expect(beides).toEqual(["methode", "begriff"])
  })
})

describe("relationen", () => {
  it("bietet bei Fachbegriffen eine kuratierte Teilmenge", () => {
    const r = relationen("begriff")
    expect(r.map((x) => x.relation)).toEqual(["related_to", "part_of"])
    // Die Richtung wird als Satz gezeigt, nicht als Pfeil-Abstraktion.
    expect(r[0].label).toBe("steht in Beziehung zu")
  })

  it("lässt `references` bewusst weg", () => {
    // Sie entsteht am Material, das den Begriff nutzt — nicht am Begriff selbst.
    expect(relationen("begriff").map((r) => r.relation)).not.toContain("references")
  })

  it("schränkt die Zieltypen ein", () => {
    const partOf = relationen("begriff").find((r) => r.relation === "part_of")
    expect(partOf.ziel).toEqual(["themengebiet"])
  })

  it("gibt für Sammlungen ohne Dialog nichts", () => {
    expect(relationen("sozialform")).toEqual([])
    expect(kannVerknuepfen("sozialform")).toBe(false)
    expect(kannVerknuepfen("begriff")).toBe(true)
  })

  it("nennt nur Relationen, die die Datenbank zulässt", () => {
    // Neun, nicht zehn: `reflects_on` fiel mit Migration 0056 weg.
    const erlaubt = new Set([
      "requires", "used_with", "part_of", "develops", "supersedes",
      "references", "follows", "derived_from", "related_to",
    ])
    for (const s of alleSammlungen()) {
      for (const r of relationen(s.typ)) expect(erlaubt.has(r.relation)).toBe(true)
    }
  })
})

describe("istStub", () => {
  it("erkennt die Markierung aus dem Verknüpfen-Dialog", () => {
    expect(istStub({ metadata: { unvollstaendig: true } })).toBe(true)
  })

  it("hält einen bloß leeren Eintrag nicht für einen Stub", () => {
    // Der Unterschied ist der Punkt: Ein Stub ist zählbar und filterbar.
    expect(istStub({ metadata: {}, content: "" })).toBe(false)
    expect(istStub({})).toBe(false)
    expect(istStub(null)).toBe(false)
  })
})
