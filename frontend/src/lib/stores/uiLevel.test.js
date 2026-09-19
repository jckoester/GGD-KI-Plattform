import { describe, it, expect } from "vitest"
import { sichtbareEintraege, verborgeneStufen, wirksameStufe } from "./uiLevel.js"

const REGISTRY = {
  rolle: "teacher",
  startstufe: 1,
  hoechste: 3,
  stufen: [
    { stufe: 1, name: "Chatten", eintraege: ["chat", "history"] },
    { stufe: 2, name: "Material", eintraege: ["library"] },
    { stufe: 3, name: "Wissen", eintraege: ["knowledge"] },
  ],
}

describe("wirksameStufe", () => {
  it("nimmt den gespeicherten Wert", () => {
    expect(wirksameStufe({ ui_level: 2 }, REGISTRY)).toBe(2)
  })

  it("fällt ohne Wert auf die Startstufe", () => {
    expect(wirksameStufe({}, REGISTRY)).toBe(1)
    expect(wirksameStufe(undefined, REGISTRY)).toBe(1)
  })

  it("klemmt einen Wert außerhalb des Bereichs", () => {
    // Ein Altwert aus einer Konfiguration mit mehr Stufen darf die Navigation nicht leeren.
    expect(wirksameStufe({ ui_level: 0 }, REGISTRY)).toBe(1)
    expect(wirksameStufe({ ui_level: 99 }, REGISTRY)).toBe(3)
  })

  it("liest eine Zahl als Zeichenkette", () => {
    expect(wirksameStufe({ ui_level: "2" }, REGISTRY)).toBe(2)
  })

  it("ignoriert Unsinn", () => {
    expect(wirksameStufe({ ui_level: "hoch" }, REGISTRY)).toBe(1)
  })

  it("liefert ohne Registry null — kein Filter, nicht Stufe 0", () => {
    expect(wirksameStufe({ ui_level: 2 }, null)).toBeNull()
  })

  it("liefert für eine Rolle ohne Stufen null", () => {
    expect(wirksameStufe({}, { rolle: null, startstufe: 1, hoechste: 1, stufen: [] })).toBeNull()
  })
})

describe("sichtbareEintraege", () => {
  it("ist kumulativ", () => {
    expect([...sichtbareEintraege(REGISTRY, 2)]).toEqual(["chat", "history", "library"])
  })

  it("zeigt auf der höchsten Stufe alles", () => {
    expect(sichtbareEintraege(REGISTRY, 3).size).toBe(4)
  })

  it("gibt ohne Registry null zurück — die Sidebar zeigt dann alles", () => {
    // Der Rückfall geht bewusst in diese Richtung: Eine wegen eines fehlgeschlagenen
    // Abrufs leere Navigation wäre der schlimmere Fehler.
    expect(sichtbareEintraege(null, 1)).toBeNull()
    expect(sichtbareEintraege(REGISTRY, null)).toBeNull()
  })
})

describe("verborgeneStufen", () => {
  it("nennt die Stufen oberhalb der eigenen", () => {
    expect(verborgeneStufen(REGISTRY, 1).map((s) => s.name)).toEqual(["Material", "Wissen"])
  })

  it("ist auf der höchsten Stufe leer", () => {
    expect(verborgeneStufen(REGISTRY, 3)).toEqual([])
  })

  it("ist ohne Registry leer — dann gibt es nichts anzubieten", () => {
    expect(verborgeneStufen(null, 1)).toEqual([])
  })
})

// ── Wächter: Sidebar und Backend sprechen dieselben Schlüssel ────────────────
// Der Zuschnitt liegt in einer YAML, die Schlüsselnamen aber im Code — auf beiden
// Seiten. Ein Tippfehler in der Sidebar (`libary`) fiele sonst nicht auf: Der Eintrag
// wäre schlicht immer sichtbar, weil `$zeigtEintrag` einen unbekannten Schlüssel nicht
// als „verborgen" erkennen kann. Genau dieser Fehler wäre stumm.

import { readFileSync } from "node:fs"

const SIDEBAR = new URL("../components/Sidebar.svelte", import.meta.url)
const LEVELS_PY = new URL("../../../../backend/app/ui/levels.py", import.meta.url)

/** Die Schlüssel, die das Backend kennt (`BEKANNTE_EINTRAEGE` in levels.py). */
function bekannteSchluessel() {
    const py = readFileSync(LEVELS_PY, "utf8")
    const block = py.slice(
        py.indexOf("BEKANNTE_EINTRAEGE = frozenset({"),
        py.indexOf("})", py.indexOf("BEKANNTE_EINTRAEGE")),
    )
    return new Set([...block.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]))
}

/** Die Schlüssel, die die Sidebar filtert. */
function sidebarSchluessel() {
    const quelle = readFileSync(SIDEBAR, "utf8")
        .replace(/<!--[\s\S]*?-->/g, "")
        .replace(/^\s*\/\/[^\n]*/gm, "")
    return new Set([...quelle.matchAll(/\$zeigtEintrag\('([a-z_]+)'\)/g)].map((m) => m[1]))
}

describe("Sidebar-Schlüssel", () => {
    it("die Suche greift überhaupt", () => {
        // Gegenprobe gegen den stummen Fehlschlag: Passt das Muster nicht mehr, fände
        // der Test nie etwas und bliebe für immer grün.
        expect(sidebarSchluessel().size).toBeGreaterThan(5)
        expect(bekannteSchluessel().size).toBeGreaterThan(5)
    })

    it("die Sidebar verwendet nur Schlüssel, die das Backend kennt", () => {
        const bekannt = bekannteSchluessel()
        const unbekannt = [...sidebarSchluessel()].filter((k) => !bekannt.has(k))
        expect(unbekannt).toEqual([])
    })

    it("Kommentare zählen nicht als Verwendung", () => {
        // Sonst hielte der Test einen erklärenden Satz für echten Code — derselbe
        // Fehler, der `farbregeln.test.js` einmal wertlos gemacht hat.
        const quelle = readFileSync(SIDEBAR, "utf8")
        expect(quelle).toContain("$zeigtEintrag(key)") // steht im Kommentar
        expect(sidebarSchluessel().has("key")).toBe(false)
    })
})
