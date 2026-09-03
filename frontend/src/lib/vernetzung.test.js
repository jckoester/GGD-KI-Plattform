import { describe, it, expect } from "vitest"
import { gruppiereKanten, KAPPUNG, NUR_ZAHL_AB } from "./vernetzung.js"

const E = { id: "ego", title: "Oxidation", category: "concept", content_type: "begriff" }
const knoten = (id, extra = {}) => ({
  id, title: id, category: "concept", content_type: "begriff", ...extra,
})
const kante = (id, from, to, relation) => ({
  id, from_node_id: from, to_node_id: to, relation,
})

function bau(edges, nodes = []) {
  return gruppiereKanten(E, { nodes: [E, ...nodes], edges })
}

describe("gruppiereKanten — Zugehörigkeit", () => {
  it("nimmt ausgehende und eingehende Kanten", () => {
    const g = bau(
      [kante("k1", "ego", "a", "part_of"), kante("k2", "b", "ego", "part_of")],
      [knoten("a"), knoten("b")],
    )
    expect(g.map((x) => x.label).sort()).toEqual(["Enthält", "Gehört zu"])
  })

  it("⚠️ lässt Kanten zwischen zwei Nachbarn weg", () => {
    // Die Nachbarschaft liefert sie mit; ohne diese Prüfung stünden sie in der Liste,
    // als gingen sie vom aktuellen Knoten aus (Fehler vom 03.09.2026).
    const g = bau([kante("k", "a", "b", "related_to")], [knoten("a"), knoten("b")])
    expect(g).toEqual([])
  })

  it("lässt Kanten ohne sichtbares Gegenstück weg", () => {
    // Der Sichtbarkeitsfilter des Servers wirkt so von selbst — nichts wird
    // anonymisiert angedeutet.
    const g = bau([kante("k", "ego", "geheim", "references")], [])
    expect(g).toEqual([])
  })

  it("verträgt fehlende Daten", () => {
    expect(gruppiereKanten(null, { nodes: [], edges: [] })).toEqual([])
    expect(gruppiereKanten(E, null)).toEqual([])
    expect(gruppiereKanten(E, {})).toEqual([])
  })
})

describe("gruppiereKanten — Richtung", () => {
  it("trennt gerichtete Relationen in zwei Gruppen mit eigenem Satz", () => {
    const g = bau(
      [kante("k1", "ego", "a", "references"), kante("k2", "b", "ego", "references")],
      [knoten("a"), knoten("b")],
    )
    const labels = g.map((x) => x.label)
    expect(labels).toContain("Verweist auf")
    expect(labels).toContain("Wird verwiesen von")
  })

  it("fasst symmetrische Relationen zusammen", () => {
    // „A steht in Beziehung zu B" heißt dasselbe wie umgekehrt — zwei Gruppen wären
    // eine Unterscheidung ohne Unterschied.
    const g = bau(
      [kante("k1", "ego", "a", "related_to"), kante("k2", "b", "ego", "related_to")],
      [knoten("a"), knoten("b")],
    )
    expect(g).toHaveLength(1)
    expect(g[0].label).toBe("Steht in Beziehung zu")
    expect(g[0].gesamt).toBe(2)
  })

  it("merkt sich die Richtung je Eintrag — nur Ausgehendes ist entfernbar", () => {
    const g = bau([kante("k", "b", "ego", "part_of")], [knoten("b")])
    expect(g[0].sichtbar[0].raus).toBe(false)
  })

  it("fällt für unbekannte Relationen auf einen lesbaren Notnamen zurück", () => {
    const g = bau([kante("k", "ego", "a", "erfunden")], [knoten("a")])
    expect(g[0].label).toBe("erfunden (raus)")
  })
})

describe("gruppiereKanten — Kappung", () => {
  const viele = (n, relation = "references") =>
    bau(
      Array.from({ length: n }, (_, i) => kante(`k${i}`, "ego", `n${i}`, relation)),
      Array.from({ length: n }, (_, i) => knoten(`n${i}`)),
    )[0]

  it("zeigt kleine Gruppen vollständig", () => {
    const g = viele(5)
    expect(g.sichtbar).toHaveLength(5)
    expect(g.weitere).toBe(0)
    expect(g.nurZahl).toBe(false)
  })

  it("kappt bei 20 und nennt den Rest", () => {
    const g = viele(KAPPUNG + 5)
    expect(g.sichtbar).toHaveLength(KAPPUNG)
    expect(g.weitere).toBe(5)
    expect(g.nurZahl).toBe(false)
  })

  it("zeigt bei sehr vielen nur noch die Zahl", () => {
    // 940 eingehende Verweise kommen im Bildungsplan real vor. Zwanzig Titel daraus
    // wären eine willkürliche Stichprobe, die nach Auswahl aussieht.
    const g = viele(NUR_ZAHL_AB + 1)
    expect(g.sichtbar).toEqual([])
    expect(g.nurZahl).toBe(true)
    expect(g.weitere).toBe(NUR_ZAHL_AB + 1)
  })

  it("die Schwelle ist ein echtes Größer", () => {
    expect(viele(NUR_ZAHL_AB).nurZahl).toBe(false)
  })
})

describe("gruppiereKanten — Reihenfolge", () => {
  it("sortiert die größten Gruppen nach oben", () => {
    const g = bau(
      [
        kante("k1", "ego", "a", "part_of"),
        kante("k2", "ego", "b", "references"),
        kante("k3", "ego", "c", "references"),
      ],
      [knoten("a"), knoten("b"), knoten("c")],
    )
    expect(g.map((x) => x.gesamt)).toEqual([2, 1])
  })
})
