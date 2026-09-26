import { describe, it, expect } from "vitest"
import {
  alleSammlungen,
  fachSammlungen,
  schuelerSammlungen,
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
  it("liefert die sechs Sammlungen mit Label und Beschreibungssatz", () => {
    const typen = alleSammlungen().map((s) => s.typ)
    expect(typen).toEqual([
      "methodenblatt",
      "operatorenblatt",
      "methode",
      "sozialform",
      "begriff",
      // Seit 26.09.2026 (Paket 9): Stoffe sind eine eigene Liste — mit Formel und
      // Prüfstatus, nicht mit Definition.
      "stoffsteckbrief",
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
    // Reihenfolge = YAML. `fassung` und `pruefstatus` kamen am 26.09.2026 dazu
    // (Paket 9/AP1): Gleichnamige Begriffe unterscheiden sich nur in der Fassung,
    // und der Prüfstatus entscheidet später über die Schülersichtbarkeit.
    expect(s.map((c) => c.name)).toEqual([
      "titel",
      "fassung",
      "fach",
      "ab_klasse",
      "pruefstatus",
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
  // ⚠️ **Über den Namen, nicht über die Position.** Die Destrukturierung
  // `const [titel, fach, abKlasse, …]` brach am 26.09.2026, als zwei Spalten dazukamen —
  // und zwar nicht an der Stelle, die sich geändert hatte, sondern in fünf Tests, die
  // mit Spalten nichts zu tun haben.
  const spalte = (name) => spalten("begriff").find((c) => c.name === name)
  const [titel, fach, abKlasse, status, geaendert] = [
    "titel", "fach", "ab_klasse", "status", "geaendert",
  ].map(spalte)

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
    expect(zellenwert({ metadata: { ab_klasse: 7 } }, aliase)).toBe("—")
  })

  it("liest die Aliase aus dem eigenen Feld, nicht aus den Metadaten", () => {
    // Seit Migration 0057 stehen sie in `node_aliases`. Käme die Spalte weiter aus
    // `metadata`, stünde in der Sammlung seither überall ein Strich.
    const [, , aliase] = spalten("methode")
    expect(zellenwert({ aliase: ["A", "B"] }, aliase)).toBe("A, B")
    expect(zellenwert({ metadata: { aliase: ["Alt"] } }, aliase)).toBe("—")
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
    //
    // ⚠️ Hier stand bis zum 26.09.2026 `quelle` als Beispiel für „fremd". Das Feld ist
    // seit Paket 9/AP1 Teil des Schemas; der Test prüfte danach das Gegenteil seiner
    // Absicht. Jetzt steht hier, was der Import schreibt und der Editor nie anzeigt.
    expect(
      metadatenAusFormular("begriff", { ab_klasse: 7 }, { import_key: "CH-042" }),
    ).toEqual({ import_key: "CH-042", ab_klasse: 7 })
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
      "stoffsteckbrief",
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
      "stoffsteckbrief",
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
    expect(beides).toEqual(["methode", "begriff", "stoffsteckbrief"])
  })
})

describe("schuelerSammlungen", () => {
  it("sind Fachbegriffe, Methoden- und Operatorenblätter", () => {
    // Was Schüler:innen im Unterricht in die Hand bekommen. Reihenfolge = YAML.
    expect(schuelerSammlungen().map((s) => s.typ)).toEqual([
      "methodenblatt",
      "operatorenblatt",
      "begriff",
      // „Was ist das für ein Stoff?" ist eine Schülerfrage — dieselbe Art wie der
      // Fachbegriff.
      "stoffsteckbrief",
    ])
  })

  it("lässt das Planungsvokabular der Lehrkraft draußen", () => {
    // `methode` führt *Unterrichts*methoden (Placemat, Galeriegang) — das
    // Vokabular des Stundenentwurfs, keine Frage, die Schüler:innen stellen.
    // `sozialform` ebenso, und sie kennt zudem kein Fach.
    const typen = schuelerSammlungen().map((s) => s.typ)
    expect(typen).not.toContain("methode")
    expect(typen).not.toContain("sozialform")
  })

  it("ist eine Teilmenge der fachgebundenen Sammlungen", () => {
    // Der Abschnitt „Nachschlagen" filtert aufs Fach der Gruppe — eine Sammlung
    // ohne Fachfilter stünde dort ungefiltert und wäre eine andere Ansicht.
    const fach = fachSammlungen().map((s) => s.typ)
    for (const s of schuelerSammlungen()) {
      expect(fach, s.typ).toContain(s.typ)
    }
  })
})

describe("relationen", () => {
  it("bietet bei Fachbegriffen eine kuratierte Teilmenge", () => {
    const r = relationen("begriff")
    expect(r.map((x) => x.relation)).toEqual([
      "related_to", "part_of", "references", "requires", "is_a",
    ])
    // Die Richtung wird als Satz gezeigt, nicht als Pfeil-Abstraktion.
    expect(r[0].label).toBe("steht in Beziehung zu")
  })

  it("⚠️ `references` zeigt hier **auf** den Bildungsplan", () => {
    // Bis zum 26.09.2026 stand hier das Gegenteil: „lässt `references` bewusst weg —
    // sie entsteht am Material, das den Begriff nutzt". Das gilt weiterhin für die
    // Richtung *Material → Begriff*. Die Gegenrichtung ist eine andere Aussage: Ein
    // Begriff verweist auf die Kompetenz, in der der Bildungsplan ihn verlangt, und
    // diese Kante entsteht am Begriff (Paket 9/AP1). Am Kompetenzknoten dürfte sie
    // nicht entstehen — der trüge sonst Tausende Rückverweise (ADR-013, Kantendichte).
    const references = relationen("begriff").find((r) => r.relation === "references")
    expect(references.ziel).toEqual(["ik_kompetenz"])
    expect(references.label).toBe("wird im Bildungsplan verlangt in")
  })

  it("kennt `is_a` als eigene Beziehungsart", () => {
    // Hierarchie ist kein `related_to` mit Beiwerk: Graphansicht und Traversierung
    // filtern nach Relationstyp (ADR-013, Nachtrag 26.09.2026).
    const isA = relationen("begriff").find((r) => r.relation === "is_a")
    expect(isA.ziel).toEqual(["begriff"])
    expect(isA.label).toBe("ist ein(e)")
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
    // Zehn: `reflects_on` fiel mit Migration 0056 weg, `is_a` kam mit 0078 dazu.
    //
    // ⚠️ **Diese Liste ist die vierte Kopie** (DB-CHECK, `models.py`,
    // `ERLAUBTE_RELATIONEN`, hier). Sie lässt sich von hier aus nicht auflösen — die
    // erzeugte `taxonomy.js` trägt die Relationen nicht, und der Generator liest nur
    // YAML, keinen Python-Code. Backend-seitig hält `test_relationen_einheitlich.py`
    // Modell und Konstante zusammen; als Todo notiert.
    const erlaubt = new Set([
      "requires", "used_with", "part_of", "develops", "supersedes",
      "references", "follows", "derived_from", "related_to", "is_a",
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
