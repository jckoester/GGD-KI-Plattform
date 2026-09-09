import { describe, it, expect, vi } from "vitest"
import { get } from "svelte/store"
import { gruppenFuerScope, gueltigeGruppenwahl } from "./myGroups.js"

const UNTERRICHT = [
  { id: 1, name: "10a Mathe", type: "teaching_group" },
  { id: 2, name: "8c Chemie", type: "teaching_group" },
]
const FACHSCHAFTEN = [
  { id: 10, name: "Fachschaft Mathematik", type: "subject_department" },
  { id: 11, name: "Fachschaft Chemie", type: "subject_department" },
]
const BEIDE = { unterricht: UNTERRICHT, fachschaften: FACHSCHAFTEN }

describe("gruppenFuerScope", () => {
  it("bietet bei `subject` die Fachschaften", () => {
    // Der eigentliche Fehler: Hier standen Unterrichtsgruppen. Ein Baustein mit
    // write_scope=subject gehört der Fachschaft, nicht einer Klasse.
    expect(gruppenFuerScope("subject", BEIDE)).toBe(FACHSCHAFTEN)
  })

  it("bietet bei `group` die Unterrichtsgruppen", () => {
    expect(gruppenFuerScope("group", BEIDE)).toBe(UNTERRICHT)
  })

  it("bietet nichts, wo keine Gruppe gebraucht wird", () => {
    for (const scope of ["private", "school", "global"]) {
      expect(gruppenFuerScope(scope, BEIDE), scope).toEqual([])
    }
  })

  it("verträgt fehlende Listen", () => {
    expect(gruppenFuerScope("subject")).toEqual([])
    expect(gruppenFuerScope("group", {})).toEqual([])
  })
})

describe("gueltigeGruppenwahl", () => {
  it("behält eine Auswahl, die es gibt", () => {
    expect(gueltigeGruppenwahl(2, UNTERRICHT)).toBe(2)
  })

  it("verwirft eine Auswahl, die nicht mehr zur Liste gehört", () => {
    // Der Fall beim Umschalten von „Gruppe" auf „Fach": Die Unterrichtsgruppe
    // steht nicht mehr zur Wahl, ihre Id aber noch im Formular — und das Backend
    // prüft den Gruppentyp nicht, nähme sie also an.
    expect(gueltigeGruppenwahl(2, FACHSCHAFTEN)).toBeNull()
  })

  it("verträgt leere Auswahl und leere Liste", () => {
    expect(gueltigeGruppenwahl(null, UNTERRICHT)).toBeNull()
    expect(gueltigeGruppenwahl(1, [])).toBeNull()
    expect(gueltigeGruppenwahl(1, undefined)).toBeNull()
  })
})

// ── Ladezustand ─────────────────────────────────────────────────────────────
// `myGroupsGeladen` trennt „noch nicht geladen" von „keine Gruppen". Ohne diese
// Unterscheidung zeigt die Schüler-Weiche auf `/subjects/[slug]` beim Aufbau kurz
// „dieses Fach ist dir nicht zugeordnet", bevor die Daten da sind.
describe("myGroupsGeladen", () => {
  it("steht auch nach einem Fehlschlag auf true", async () => {
    // Sonst bliebe die Oberfläche bei einem Netzfehler ewig im Ladezustand —
    // ein stiller Ausfall, der wie eine hängende Seite aussieht.
    vi.resetModules()
    vi.doMock("$lib/api.js", () => ({
      getMyGroups: () => Promise.reject(new Error("Netz weg")),
    }))
    const { myGroupsGeladen, refreshMyGroups, myGroups } = await import("./myGroups.js")
    expect(get(myGroupsGeladen)).toBe(false)

    await refreshMyGroups()

    expect(get(myGroupsGeladen)).toBe(true)
    expect(get(myGroups)).toEqual([])
    vi.doUnmock("$lib/api.js")
  })

  it("steht nach erfolgreichem Abruf auf true und trägt die Gruppen", async () => {
    vi.resetModules()
    vi.doMock("$lib/api.js", () => ({
      getMyGroups: () => Promise.resolve({ items: UNTERRICHT }),
    }))
    const { myGroupsGeladen, refreshMyGroups, myTeachingGroups } = await import("./myGroups.js")

    await refreshMyGroups()

    expect(get(myGroupsGeladen)).toBe(true)
    expect(get(myTeachingGroups).map((g) => g.id)).toEqual([1, 2])
    vi.doUnmock("$lib/api.js")
  })
})
