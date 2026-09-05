import { describe, it, expect } from "vitest"
import { mitPhasenKennungen } from "./planner.js"

describe("mitPhasenKennungen", () => {
  it("ergänzt eine fehlende Kennung", () => {
    const [phase] = mitPhasenKennungen([{ name: "Erarbeitung" }])
    expect(phase.id).toBeTruthy()
    expect(phase.name).toBe("Erarbeitung")
  })

  it("ergänzt auch, wenn der Server null schickt", () => {
    // ⚠️ Der Fall, an dem die frühere Fassung stillschweigend scheiterte:
    // `{ id: p.id ?? crypto.randomUUID(), ...p }` — der Spread stand *hinter* der
    // Zuweisung und überschrieb die eben erzeugte Kennung wieder mit null.
    // Der Server liefert genau das: `patch_lesson` speichert mit
    // `exclude_none=False`, eine Phase ohne Kennung wird als `"id": null` abgelegt.
    const [phase] = mitPhasenKennungen([{ id: null, name: "P" }])
    expect(phase.id).toBeTruthy()
    expect(phase.id).not.toBeNull()
  })

  it("ergänzt bei leerer Zeichenkette", () => {
    const [phase] = mitPhasenKennungen([{ id: "  ", name: "P" }])
    expect(phase.id.trim()).toBeTruthy()
  })

  it("lässt eine vorhandene Kennung unangetastet", () => {
    // Sie neu zu vergeben bräche `phasen_status` und übertragene Phasen.
    const [phase] = mitPhasenKennungen([{ id: "p1", name: "P" }])
    expect(phase.id).toBe("p1")
  })

  it("vergibt untereinander verschiedene Kennungen", () => {
    const phasen = mitPhasenKennungen([{ name: "A" }, { name: "B" }, { name: "C" }])
    expect(new Set(phasen.map((p) => p.id)).size).toBe(3)
  })

  it("ändert einen fertigen Stand beim zweiten Lauf nicht", () => {
    const einmal = mitPhasenKennungen([{ name: "A" }, { id: "p2", name: "B" }])
    const zweimal = mitPhasenKennungen(einmal)
    expect(zweimal.map((p) => p.id)).toEqual(einmal.map((p) => p.id))
  })

  it("erhält die übrigen Felder", () => {
    const [phase] = mitPhasenKennungen([
      { name: "P", dauer_min: 15, material: [{ typ: "node", node_id: "abc" }] },
    ])
    expect(phase.dauer_min).toBe(15)
    expect(phase.material).toEqual([{ typ: "node", node_id: "abc" }])
  })

  it("verträgt leere und fehlende Eingaben", () => {
    expect(mitPhasenKennungen([])).toEqual([])
    expect(mitPhasenKennungen(null)).toEqual([])
    expect(mitPhasenKennungen(undefined)).toEqual([])
  })
})
