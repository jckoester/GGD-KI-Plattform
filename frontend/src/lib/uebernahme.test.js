import { describe, it, expect } from "vitest"
import {
  ablaufHinweis,
  brauchtGruppe,
  erfolgsMeldung,
  knopfBeschriftung,
  nutzlast,
  scopeVorgabe,
  typOptionen,
} from "./uebernahme.js"
import { CONTENT_TYPE_LABELS } from "./taxonomy.js"

const LEHRKRAFT = {
  kind: "document",
  uebernehmbar: true,
  typen: ["lerntext", "arbeitsblatt"],
  scopes_erzwungen: null,
  vorhandener_baustein_id: null,
}

const SCHUELERIN = {
  kind: "document",
  uebernehmbar: true,
  typen: ["schuelertext", "lernplan"],
  scopes_erzwungen: ["private", "private"],
  vorhandener_baustein_id: null,
}

describe("typOptionen", () => {
  it("beschriftet deutsch und sortiert nach Label", () => {
    expect(typOptionen(LEHRKRAFT)).toEqual([
      { key: "arbeitsblatt", label: CONTENT_TYPE_LABELS.arbeitsblatt },
      { key: "lerntext", label: CONTENT_TYPE_LABELS.lerntext },
    ])
  })

  it("verträgt einen fehlenden Vorschlag", () => {
    expect(typOptionen(null)).toEqual([])
    expect(typOptionen({})).toEqual([])
  })
})

describe("scopeVorgabe", () => {
  it("übernimmt die Vorgabe der Taxonomie", () => {
    expect(scopeVorgabe(LEHRKRAFT, "arbeitsblatt")).toEqual({
      read: "group",
      write: "private",
      fest: false,
    })
  })

  it("meldet eine erzwungene Sichtbarkeit als fest", () => {
    // Die Oberfläche zeigt dann kein Auswahlfeld — ein Angebot, das der Server
    // ohnehin überschreibt, wäre eine Lüge.
    expect(scopeVorgabe(SCHUELERIN, "schuelertext")).toEqual({
      read: "private",
      write: "private",
      fest: true,
    })
  })

  it("fällt bei unbekanntem Typ auf school/private zurück", () => {
    expect(scopeVorgabe(LEHRKRAFT, "gibt_es_nicht")).toMatchObject({
      read: "school",
      write: "private",
    })
  })
})

describe("brauchtGruppe", () => {
  it("nur group und subject tragen eine Gruppe", () => {
    expect(brauchtGruppe("group")).toBe(true)
    expect(brauchtGruppe("subject")).toBe(true)
    for (const s of ["private", "school", "global", null, undefined]) {
      expect(brauchtGruppe(s)).toBe(false)
    }
  })
})

describe("nutzlast", () => {
  it("baut die Felder des Endpunkts", () => {
    expect(
      nutzlast({
        contentType: "arbeitsblatt",
        titel: "  Satz des Thales  ",
        readScope: "group",
        writeScope: "private",
        readGroupId: 7,
        validUntil: "2027-07-28",
        schuljahr: "2026/2027",
      }),
    ).toEqual({
      content_type: "arbeitsblatt",
      title: "Satz des Thales",
      read_scope: "group",
      write_scope: "private",
      read_scope_group_id: 7,
      write_scope_group_id: null,
      valid_until: "2027-07-28",
      schuljahr: "2026/2027",
    })
  })

  it("nullt eine Gruppe, die der Scope nicht trägt", () => {
    // Der stille Fall: Erst „Gruppe" gewählt, dann auf „Schule" umgestellt — die ID
    // bliebe im Formular stehen und hinge den Baustein an eine Klasse, die in seiner
    // Sichtbarkeit gar nicht vorkommt.
    const p = nutzlast({
      contentType: "lerntext",
      titel: "Text",
      readScope: "school",
      writeScope: "private",
      readGroupId: 7,
      writeGroupId: 7,
    })
    expect(p.read_scope_group_id).toBeNull()
    expect(p.write_scope_group_id).toBeNull()
  })

  it("macht aus leerem Titel und leerem Datum null", () => {
    const p = nutzlast({ contentType: "lerntext", titel: "   " })
    expect(p.title).toBeNull()
    expect(p.valid_until).toBeNull()
    expect(p.schuljahr).toBeNull()
  })
})

describe("knopfBeschriftung", () => {
  it("heißt beim ersten Mal speichern", () => {
    expect(knopfBeschriftung(LEHRKRAFT)).toBe("Als Baustein speichern")
  })

  it("heißt beim zweiten Mal aktualisieren", () => {
    expect(knopfBeschriftung({ ...LEHRKRAFT, vorhandener_baustein_id: "x" })).toBe(
      "Baustein aktualisieren",
    )
  })
})

describe("erfolgsMeldung", () => {
  it("unterscheidet neu, neue Fassung und nichts zu tun", () => {
    expect(erfolgsMeldung({ created: true, ersetzt_node_id: null })).toBe(
      "Als Baustein gespeichert.",
    )
    expect(erfolgsMeldung({ created: true, ersetzt_node_id: "alt" })).toContain("Archiv")
    expect(erfolgsMeldung({ created: false })).toContain("bereits gespeichert")
  })
})

describe("ablaufHinweis", () => {
  it("warnt bei Arten, die der Server aufs Schuljahresende setzt", () => {
    expect(ablaufHinweis("schuelertext", "")).toContain("Schuljahres")
  })

  it("schweigt, wenn ein Datum gewählt wurde", () => {
    expect(ablaufHinweis("schuelertext", "2027-07-28")).toBeNull()
  })

  it("schweigt bei Arten ohne Vorbelegung", () => {
    expect(ablaufHinweis("lerntext", "")).toBeNull()
  })
})
