import { describe, it, expect } from "vitest"
import { CATEGORY_ICONS, FALLBACK_ICON, NODE_ICONS } from "./node_icons.js"
import { CONTENT_TYPES } from "./taxonomy.js"

/**
 * `node_icons.js` wird aus `taxonomy.yaml` erzeugt. Vollständigkeit prüft deshalb
 * schon die Startprüfung des Backends (`taxonomy_check.py`), und ein erfundener
 * Komponentenname bricht den Build. Was hier bleibt, ist die **Gestaltungsfrage**,
 * die keine der beiden Prüfungen beantworten kann: Unterscheiden die Symbole
 * überhaupt etwas?
 */
const ALLE_TYPEN = Object.values(CONTENT_TYPES).flat()

describe("NODE_ICONS", () => {
  it("deckt die Taxonomie ab — Gegenprobe zum Generator", () => {
    // Nicht die eigentliche Absicherung (das ist taxonomy_check.py), aber es fängt
    // den Fall ab, dass jemand die Datei von Hand ändert oder den Generator nach
    // einer YAML-Änderung vergisst.
    const fehlend = ALLE_TYPEN.filter((t) => !NODE_ICONS[t])
    expect(fehlend, `ohne Symbol: ${fehlend.join(", ")}`).toEqual([])
  })

  it("unterscheidet die Typen einer Kategorie sichtbar", () => {
    // Der eigentliche Zweck: In `artifact` — der Kategorie von „Meine Bausteine" —
    // muss jede Zeile ein anderes Symbol tragen können. Vorher trugen dort alle
    // dasselbe Paket, weil 30 der 41 Typen im Kategorie-Fallback landeten.
    for (const [kategorie, typen] of Object.entries(CONTENT_TYPES)) {
      const symbole = typen.map((t) => NODE_ICONS[t])
      const verschiedene = new Set(symbole).size
      expect(
        verschiedene / symbole.length,
        `${kategorie}: nur ${verschiedene} Symbole für ${symbole.length} Typen`,
      ).toBeGreaterThan(0.7)
    }
  })

  it("gibt Artefakten durchweg eigene Symbole", () => {
    // Schärfer als die Quote oben, weil hier der Anlass lag: „Meine Bausteine"
    // zeigt fast ausschließlich Artefakte.
    const symbole = CONTENT_TYPES.artifact.map((t) => NODE_ICONS[t])
    expect(new Set(symbole).size).toBe(symbole.length)
  })

  it("hat einen Rückfall je Kategorie und einen letzten", () => {
    for (const kategorie of Object.keys(CONTENT_TYPES)) {
      expect(CATEGORY_ICONS[kategorie], kategorie).toBeTruthy()
    }
    expect(FALLBACK_ICON).toBeTruthy()
  })
})
