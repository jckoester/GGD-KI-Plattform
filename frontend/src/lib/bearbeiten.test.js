import { describe, it, expect } from "vitest"
import { bearbeitenZiel } from "./bearbeiten.js"

const CHEMIE = { id: 6, slug: "chemie", name: "Chemie" }

const knoten = (extra) => ({
  id: "n1", content_type: "arbeitsblatt", subject_id: 6,
  write_scope_group_id: null, ...extra,
})

describe("Planungsobjekte", () => {
  it("führen den Stundenentwurf in den Planer — direkt auf die Stunde", () => {
    const z = bearbeitenZiel(
      knoten({ content_type: "unterrichtsstunde", write_scope_group_id: 7 }),
      CHEMIE,
    )
    expect(z.art).toBe("planer")
    expect(z.url).toBe("/subjects/chemie/groups/7/planner/lessons/n1")
    expect(z.label).toBe("Im Planer öffnen")
  })

  it("führen Jahresplan und Einheit auf die Planer-Übersicht", () => {
    for (const typ of ["jahresplan", "unterrichtseinheit"]) {
      const z = bearbeitenZiel(
        knoten({ content_type: typ, write_scope_group_id: 7 }),
        CHEMIE,
      )
      expect(z.url).toBe("/subjects/chemie/groups/7/planner")
    }
  })

  it("nehmen die Lesegruppe, wenn keine Schreibgruppe gesetzt ist", () => {
    const z = bearbeitenZiel(
      knoten({
        content_type: "unterrichtsstunde",
        write_scope_group_id: null,
        read_scope_group_id: 9,
      }),
      CHEMIE,
    )
    expect(z.url).toBe("/subjects/chemie/groups/9/planner/lessons/n1")
  })

  it("bieten ohne Gruppe keinen Knopf, sondern sagen wo es hingehört", () => {
    // Von Hand angelegte Planungsknoten gibt es; ein Editor, der Phasen als JSON zeigt,
    // wäre dort die falsche Antwort.
    const z = bearbeitenZiel(knoten({ content_type: "unterrichtsstunde" }), CHEMIE)
    expect(z.art).toBe("keiner")
    expect(z.url).toBeNull()
    expect(z.hinweis).toMatch(/Planer/)
  })

  it("bieten ohne bekanntes Fach ebenfalls keinen Knopf", () => {
    const z = bearbeitenZiel(
      knoten({ content_type: "unterrichtsstunde", write_scope_group_id: 7 }),
      null,
    )
    expect(z.art).toBe("keiner")
    expect(z.hinweis).toBeTruthy()
  })
})

describe("Sammlungen", () => {
  it("führen in ihren Formular-Editor", () => {
    const z = bearbeitenZiel(knoten({ content_type: "begriff" }), CHEMIE)
    expect(z.art).toBe("sammlung")
    expect(z.url).toBe("/knowledge/collections/begriff/n1/edit")
  })

  it("reichen den Rückweg weiter", () => {
    const z = bearbeitenZiel(
      knoten({ content_type: "begriff" }), CHEMIE, "/knowledge/collections/begriff?q=x",
    )
    expect(z.url).toContain("back=%2Fknowledge%2Fcollections%2Fbegriff%3Fq%3Dx")
  })
})

describe("Alles Übrige", () => {
  it("bleibt im allgemeinen Editor", () => {
    const z = bearbeitenZiel(knoten(), CHEMIE)
    expect(z.art).toBe("allgemein")
    expect(z.url).toBe("/knowledge/n1/edit")
  })

  it("verträgt einen fehlenden Knoten", () => {
    expect(bearbeitenZiel(null).art).toBe("keiner")
  })
})
