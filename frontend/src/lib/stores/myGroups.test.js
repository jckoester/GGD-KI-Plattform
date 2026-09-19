import { describe, it, expect, vi } from "vitest"
import { get } from "svelte/store"
import { readFileSync } from "node:fs"
import { auswahlMitBestand, fachWirdAngeboten, freigegebeneGruppen, gruppenFuerScope, gueltigeGruppenwahl } from "./myGroups.js"

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


// ── Aktuelle und frühere Gruppen (AP8) ──────────────────────────────────────

describe("aktuelle und frühere Unterrichtsgruppen", () => {
  const laden = async (items) => {
    vi.resetModules()
    vi.doMock("$lib/api.js", () => ({
      getMyGroups: () => Promise.resolve({ items }),
    }))
    const mod = await import("./myGroups.js")
    await mod.refreshMyGroups()
    return mod
  }

  const GRUPPEN = [
    { id: 1, name: "Mathe 10a", type: "teaching_group", subject_id: 1, aktuell: true },
    { id: 2, name: "Mathe 9c", type: "teaching_group", subject_id: 1, aktuell: false,
      letztes_schuljahr: "2025/26" },
    { id: 3, name: "Fachschaft", type: "subject_department", subject_id: 1, aktuell: true },
  ]

  it("trennt nach dem Kennzeichen des Backends", async () => {
    const { aktuelleTeachingGroups, fruehereTeachingGroups } = await laden(GRUPPEN)
    expect(get(aktuelleTeachingGroups).map(g => g.id)).toEqual([1])
    expect(get(fruehereTeachingGroups).map(g => g.id)).toEqual([2])
    vi.doUnmock("$lib/api.js")
  })

  it("zeigt ohne das Feld alles als aktuell", async () => {
    // Eine ältere Antwort soll alles zeigen, nicht nichts — `aktuell !== false`, nicht
    // `aktuell === true`. Andersherum verschwänden bei einem Fehlschlag alle Gruppen.
    const ohneFeld = [{ id: 9, name: "Alt", type: "teaching_group", subject_id: 1 }]
    const { aktuelleTeachingGroups, fruehereTeachingGroups } = await laden(ohneFeld)
    expect(get(aktuelleTeachingGroups).map(g => g.id)).toEqual([9])
    expect(get(fruehereTeachingGroups)).toEqual([])
    vi.doUnmock("$lib/api.js")
  })

  it("nimmt nur Unterrichtsgruppen, keine Fachschaften", async () => {
    const { aktuelleTeachingGroups } = await laden(GRUPPEN)
    expect(get(aktuelleTeachingGroups).every(g => g.type === "teaching_group")).toBe(true)
    vi.doUnmock("$lib/api.js")
  })
})


describe("auswahlMitBestand", () => {
  const ALLE = [
    { id: 1, name: "aktuell", aktuell: true },
    { id: 2, name: "früher", aktuell: false },
    { id: 3, name: "auch aktuell", aktuell: true },
  ]

  it("zeigt für einen neuen Eintrag nur die aktuellen", () => {
    expect(auswahlMitBestand(ALLE, null).map(g => g.id)).toEqual([1, 3])
  })

  it("behält die bereits gewählte frühere Gruppe", () => {
    // Sonst setzte `gueltigeGruppenwahl` die Wahl auf null, und beim nächsten Speichern
    // wäre die Zuordnung weg — ohne dass jemand sie angefasst hätte.
    expect(auswahlMitBestand(ALLE, 2).map(g => g.id)).toEqual([1, 3, 2])
  })

  it("verdoppelt eine bereits aktuelle Wahl nicht", () => {
    expect(auswahlMitBestand(ALLE, 1).map(g => g.id)).toEqual([1, 3])
  })

  it("erfindet nichts, wenn die gewählte Gruppe gar nicht dabei ist", () => {
    expect(auswahlMitBestand(ALLE, 99).map(g => g.id)).toEqual([1, 3])
  })

  it("zeigt ohne das Feld alles — etwa die Gesamtliste des Admins", () => {
    const ohneFeld = [{ id: 5, name: "fremde Gruppe" }]
    expect(auswahlMitBestand(ohneFeld, null).map(g => g.id)).toEqual([5])
  })
})

// ── Erprobungsbetrieb: Fachsichtbarkeit für Schüler:innen ────────────────────
// Die Regel steht bewusst **einmal** als Funktion da und nicht zweimal als Bedingung
// in den Stores: Fachübersicht und Chat-Auswahlfeld müssen dieselbe Antwort geben,
// sonst ließe sich ein ausgeblendetes Fach im Chat weiterhin anwählen.

const KURSE = [
  { id: 1, name: "M 9d", subject_id: 1, student_visible: true },
  { id: 2, name: "D 9d", subject_id: 2, student_visible: false },
  { id: 3, name: "Ph 9d", subject_id: 3, student_visible: false },
]

describe("freigegebeneGruppen", () => {
  it("lässt im Regelbetrieb alles durch", () => {
    expect(freigegebeneGruppen(KURSE, false)).toBe(KURSE)
  })

  it("behält im Erprobungsbetrieb nur die freigegebenen", () => {
    expect(freigegebeneGruppen(KURSE, true).map((g) => g.id)).toEqual([1])
  })

  it("blendet ohne Freigabe alles aus", () => {
    // Der Fall, den Jans Gegenbeispiel erzwingt: Eine Lehrkraft nimmt mit Gruppe 2 in
    // einem Fach teil und unterrichtet dieselbe Gruppe in einem zweiten. Das zweite
    // Fach darf nicht mitkommen, nur weil die Lehrkraft angemeldet ist.
    const ohne = KURSE.map((g) => ({ ...g, student_visible: false }))
    expect(freigegebeneGruppen(ohne, true)).toEqual([])
  })

  it("wertet ein fehlendes Feld als nicht freigegeben", () => {
    // Robustheit gegen eine ältere Antwort ohne das Feld: Im Zweifel nicht zeigen —
    // hier ist das die sichere Richtung, anders als beim Konfigurationsschalter.
    expect(freigegebeneGruppen([{ id: 9, subject_id: 1 }], true)).toEqual([])
  })
})

describe("beide Schüleransichten fragen dieselbe Funktion", () => {
    // Wächter über die Aufteilung, nicht über das Verhalten: Fachübersicht und
    // Auswahlfeld müssen dieselbe Antwort geben. Wer die Bedingung an einer Stelle
    // wieder ausschreibt, bekommt zwei Regeln, die auseinanderlaufen können — und
    // ein im Chat anwählbares Fach, das in der Übersicht fehlt.
    //
    // Was der Test NICHT kann: eine *neue*, dritte Ansicht bemerken. Dafür gibt es
    // keinen Anker im Quelltext; er hält nur die beiden vorhandenen zusammen.
    const DATEIEN = ["sidebarSections.js", "subjectPickerItems.js"]

    for (const datei of DATEIEN) {
        it(`${datei} ruft freigegebeneGruppen auf`, () => {
            const quelle = readFileSync(new URL(datei, import.meta.url), "utf8")
            expect(quelle).toContain("freigegebeneGruppen(")
        })

        it(`${datei} prüft student_visible nicht selbst`, () => {
            const quelle = readFileSync(new URL(datei, import.meta.url), "utf8")
                .replace(/\/\*[\s\S]*?\*\//g, "")
                .replace(/^\s*\/\/[^\n]*/gm, "")
            expect(quelle).not.toContain("student_visible")
        })
    }
})

describe("fachWirdAngeboten", () => {
  it("zeigt im Regelbetrieb ein Fach mit eigenem Chat", () => {
    expect(fachWirdAngeboten({ chats: 1, fachHatAssistent: false, erprobung: false })).toBe(true)
  })

  it("zeigt im Regelbetrieb ein Fach mit Assistent", () => {
    expect(fachWirdAngeboten({ chats: 0, fachHatAssistent: true, erprobung: false })).toBe(true)
  })

  it("verbirgt im Regelbetrieb ein Fach ohne beides", () => {
    expect(fachWirdAngeboten({ chats: 0, fachHatAssistent: false, erprobung: false })).toBe(false)
  })

  it("zeigt im Erprobungsbetrieb auch ein Fach ohne beides", () => {
    // Der Fall vom 19.09.2026: frisch freigegebene Gruppe, null Chats, kein
    // fachgebundener Assistent. Ohne diese Ausnahme sähe der Freigabe-Schalter
    // kaputt aus — und niemand könnte den ersten Chat anlegen, weil dafür das
    // Fach sichtbar sein müsste.
    expect(fachWirdAngeboten({ chats: 0, fachHatAssistent: false, erprobung: true })).toBe(true)
  })
})
